# Batch Inpaint Hang Issue - Diagnostic Fix

## Problem Description

When running batch clean (detect → mask → inpaint) on multiple pages, the system hangs after completing parallel inpainting on the first page and doesn't progress to subsequent pages.

### Symptoms from Logs
```
2026-08-18 16:38:57,190 [INFO] houmi-parallel-inpaint: Starting parallel inpainting with 4 workers for 8 regions
2026-08-18 16:39:02,376 [INFO] houmi-parallel-inpaint: Parallel inpainting completed: 8/8 regions
```

After this, no further logs appear. The system appears frozen - no progress to page 2, no database updates, no WebSocket notifications.

## Root Cause Analysis

The issue likely stems from one of these points after parallel inpainting completes:

1. **Silent exception in parallel inpaint return** - ThreadPoolExecutor may swallow exceptions
2. **File I/O blocking** - `cv2_imwrite_unicode` may hang on large files or disk issues
3. **Database commit deadlock** - SQLAlchemy commit may block if transaction is stuck
4. **Missing page refresh** - Frontend waiting for updates that never come

## Changes Made

### 1. Enhanced Logging in `inpainter.py`

Added debug logs at critical points in `clean_page_text()`:

```python
# After parallel inpainting
logger.info(f"Inpainting phase completed (parallel={use_parallel}), preparing to save output")

# Before/after saving cleaned image
logger.info(f"Saving cleaned image for page {page_id}")
logger.info(f"Writing inpainted image to: {output_path}")
cv2_imwrite_unicode(str(output_path), final_img)
logger.info(f"Inpainted image saved successfully")

# Before/after preview save
logger.info(f"Writing preview image to: {preview_inpainted_path}")
cv2_imwrite_unicode(str(preview_inpainted_path), preview_inpainted)
logger.info(f"Preview image saved successfully")

# Before/after database commit
logger.info(f"Updating database for page {page_id}")
logger.info(f"Committing database changes for page {page_id}")
db.commit()
logger.info(f"Database commit successful for page {page_id}")
```

### 2. Enhanced Logging in `pipeline.py`

Added debug logs in the batch pipeline inpaint step:

```python
# Before clean_page_text
logger.info(f"Starting clean_page_text for page {page.id}")
clean_page_text(page.id, db, cancel_check=check_cancel_requested)

# After clean_page_text returns
logger.info(f"clean_page_text completed for page {page.id}, refreshing page from database")
db.refresh(page)

# After refresh
logger.info(f"Page refreshed, broadcasting completion")
ws_manager.broadcast_sync(project_id, {
    "type": "page_inpaint_complete",
    "page_id": page.id,
    "status": "success",
})
logger.info(f"Inpaint completion broadcasted, checking for cancellation")
```

### 3. Improved Exception Handling

Enhanced exception logging in `parallel_inpaint.py`:

```python
except Exception as parallel_error:
    logger.warning(f"Parallel inpainting failed, falling back to sequential: {parallel_error}", exc_info=True)
    use_parallel = False
```

Added `exc_info=True` to log full stack traces for better debugging.

### 4. Added WebSocket Notification

Added immediate WebSocket broadcast after each page completes inpainting:

```python
ws_manager.broadcast_sync(project_id, {
    "type": "page_inpaint_complete",
    "page_id": page.id,
    "status": "success",
})
```

This ensures the frontend receives updates even if the batch progress broadcast has issues.

## Testing Instructions

Run the batch clean process and monitor logs for these checkpoint messages:

1. ✓ `"Parallel inpainting completed: X/X regions"` - Parallel work finished
2. ✓ `"Inpainting phase completed"` - Return from parallel function successful
3. ✓ `"Saving cleaned image for page"` - Entered save phase
4. ✓ `"Inpainted image saved successfully"` - File write completed
5. ✓ `"Database commit successful"` - Database updated
6. ✓ `"clean_page_text completed for page"` - Returned to pipeline
7. ✓ `"Inpaint completion broadcasted"` - WebSocket sent

### Diagnostic Script

Run `backend/test_batch_inpaint.py` to see checkpoint descriptions:

```bash
python backend/test_batch_inpaint.py
```

### Interpreting Hang Location

- **Hangs before checkpoint 2**: Issue with parallel inpaint return or exception handling
- **Hangs at checkpoint 2-3**: File I/O issue (disk full, permissions, large file)
- **Hangs at checkpoint 4**: Database commit issue (deadlock, connection lost)
- **Hangs at checkpoint 5-6**: Batch pipeline loop issue
- **Hangs after checkpoint 6**: Frontend update mechanism issue

## Expected Behavior After Fix

After parallel inpainting completes for page 1:
1. System saves cleaned image and preview
2. Updates database with inpainted_image_path
3. Broadcasts WebSocket notification
4. Immediately proceeds to page 2
5. Repeats for all 24 pages

Logs should show continuous progress:
```
[INFO] houmi-parallel-inpaint: Parallel inpainting completed: 8/8 regions
[INFO] houmi-inpainter: Inpainted image saved successfully
[INFO] houmi-inpainter: Database commit successful for page <id>
[INFO] houmi-pipeline-router: clean_page_text completed for page <id>
[INFO] houmi-pipeline-router: Inpaint completion broadcasted
[INFO] houmi-ws: WebSocket broadcast sent to project <id>
[INFO] houmi-parallel-inpaint: Starting parallel inpainting... [page 2]
```

## Additional Investigation Needed

If the issue persists after these logging improvements, check:

1. **ThreadPoolExecutor context manager** - May need explicit shutdown
2. **SQLAlchemy session state** - May need session.expire_all() after each page
3. **cv2_imwrite_unicode implementation** - May have blocking behavior
4. **WebSocket manager** - May be blocking if client disconnected
5. **Memory pressure** - Large images may cause GC pauses

## Files Modified

- `backend/app/services/inpainter.py` - Added debug logging throughout `clean_page_text()`
- `backend/app/routes/pipeline.py` - Added debug logging and WebSocket broadcast in batch pipeline
- `backend/app/services/parallel_inpaint.py` - Enhanced exception logging
- `backend/test_batch_inpaint.py` - Created diagnostic script

## Next Steps

1. Run batch clean and monitor logs to identify exact hang location
2. Based on checkpoint where it hangs, apply targeted fix:
   - **Before checkpoint 2**: Add explicit exception re-raising in parallel_inpaint
   - **At checkpoint 3**: Add timeout to cv2_imwrite_unicode or use async I/O
   - **At checkpoint 4**: Add db.expire_all() or use separate session per page
3. Once hang location identified, implement specific fix and test

---

**Date**: 2026-08-18  
**Reporter**: User  
**Status**: Diagnostic logging added, awaiting test results  
**Priority**: High - Blocks batch processing workflow
