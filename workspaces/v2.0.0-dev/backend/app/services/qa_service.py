"""
Quality Assurance (QA) and Sanity Checking Service for Houmi Studio.
Performs automated preflight validation across text blocks, pages, and projects.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.all_models import TextBlock, Page, Project
import logging

logger = logging.getLogger('houmi-qa-service')

THAI_FLOATING_DIACRITICS = {
    '\u0e31', '\u0e34', '\u0e35', '\u0e36', '\u0e37',
    '\u0e38', '\u0e39', '\u0e3a', '\u0e47',
    '\u0e48', '\u0e49', '\u0e4a', '\u0e4b',
    '\u0e4c', '\u0e4d', '\u0e4e',
}


def audit_block_qa(block: TextBlock) -> List[Dict[str, Any]]:
    issues = []
    src = (block.source_text or '').strip()
    trans = (block.translation or '').strip()

    # 1. Untranslated Bubble
    if src and not trans:
        issues.append({
            'code': 'UNTRANSLATED_BUBBLE',
            'severity': 'warning',
            'message': 'พบข้อความต้นฉบับแต่ยังไม่ได้แปล',
            'block_id': str(block.id),
            'block_index': block.block_index,
            'x': block.x,
            'y': block.y,
            'width': block.width,
            'height': block.height,
        })

    # 2. Empty Block
    if not src and not trans:
        issues.append({
            'code': 'EMPTY_BLOCK',
            'severity': 'info',
            'message': 'กล่องข้อความว่างเปล่า',
            'block_id': str(block.id),
            'block_index': block.block_index,
            'x': block.x,
            'y': block.y,
            'width': block.width,
            'height': block.height,
        })

    # 3. Low OCR Confidence
    if src and block.confidence is not None and 0.0 < block.confidence < 0.45:
        pct = int(block.confidence * 100)
        issues.append({
            'code': 'LOW_OCR_CONFIDENCE',
            'severity': 'info',
            'message': f'ความมั่นใจ OCR ค่อนข้างต่ำ ({pct}%)',
            'block_id': str(block.id),
            'block_index': block.block_index,
            'confidence': round(float(block.confidence), 3),
            'x': block.x,
            'y': block.y,
            'width': block.width,
            'height': block.height,
        })

    # 4. Text Overflow Detection
    if trans:
        container_w = block.smart_width if (block.smart_width and block.smart_width > 10) else block.width
        container_h = block.smart_height if (block.smart_height and block.smart_height > 10) else block.height
        
        lines = [line.strip() for line in trans.split('\n') if line.strip()]
        if lines and container_w > 0 and container_h > 0:
            font_size = block.font_size or 24.0
            line_height = font_size * 1.25
            total_text_h = len(lines) * line_height
            max_line_len = max(len(line) for line in lines)
            est_char_w = font_size * 0.55
            est_text_w = max_line_len * est_char_w

            w_overflow_ratio = (est_text_w - container_w) / container_w
            h_overflow_ratio = (total_text_h - container_h) / container_h

            if w_overflow_ratio > 0.15 or h_overflow_ratio > 0.15:
                max_overflow = max(w_overflow_ratio, h_overflow_ratio)
                pct_over = int(max_overflow * 100)
                issues.append({
                    'code': 'TEXT_OVERFLOW',
                    'severity': 'warning',
                    'message': f'ข้อความอาจล้นขอบบอลลูน (~{pct_over}%)',
                    'block_id': str(block.id),
                    'block_index': block.block_index,
                    'overflow_percent': pct_over,
                    'container_width': container_w,
                    'container_height': container_h,
                    'x': block.x,
                    'y': block.y,
                    'width': block.width,
                    'height': block.height,
                })

    # 5. Thai Diacritic Check
    if trans and trans[0] in THAI_FLOATING_DIACRITICS:
        issues.append({
            'code': 'THAI_FLOATING_DIACRITIC',
            'severity': 'warning',
            'message': f'ข้อความขึ้นต้นด้วยวรรณยุกต์/สระลอย {trans[0]} โดยไม่มีพยัญชนะ',
            'block_id': str(block.id),
            'block_index': block.block_index,
            'x': block.x,
            'y': block.y,
            'width': block.width,
            'height': block.height,
        })

    return issues


def audit_page_qa(page_id: str, db: Session) -> Dict[str, Any]:
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        return {'error': 'Page not found', 'issues': [], 'summary': {}}

    issues = []
    blocks = db.query(TextBlock).filter(TextBlock.page_id == page_id).order_by(TextBlock.block_index).all()

    for block in blocks:
        issues.extend(audit_block_qa(block))

    has_translations = any(bool(b.translation and b.translation.strip()) for b in blocks)
    if has_translations and not page.inpainted_image_path:
        issues.append({
            'code': 'MISSING_INPAINT_IMAGE',
            'severity': 'warning',
            'message': 'หน้านี้มีคำแปลแต่ยังไม่ได้ลบข้อความต้นฉบับ (Inpainting)',
            'page_id': page_id,
        })

    errors_count = sum(1 for i in issues if i.get('severity') == 'error')
    warnings_count = sum(1 for i in issues if i.get('severity') == 'warning')
    info_count = sum(1 for i in issues if i.get('severity') == 'info')

    return {
        'page_id': page_id,
        'page_number': page.page_number,
        'total_blocks': len(blocks),
        'total_issues': len(issues),
        'summary': {
            'errors': errors_count,
            'warnings': warnings_count,
            'info': info_count,
            'is_clean': len(issues) == 0,
        },
        'issues': issues,
    }


def audit_project_qa(project_id: str, db: Session) -> Dict[str, Any]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {'error': 'Project not found', 'pages': [], 'summary': {}}

    pages_audit = []
    total_blocks = 0
    total_issues = 0
    total_errors = 0
    total_warnings = 0
    total_info = 0

    pages = db.query(Page).filter(Page.project_id == project_id).order_by(Page.page_number).all()
    for page in pages:
        p_audit = audit_page_qa(str(page.id), db)
        pages_audit.append(p_audit)
        total_blocks += p_audit['total_blocks']
        total_issues += p_audit['total_issues']
        total_errors += p_audit['summary']['errors']
        total_warnings += p_audit['summary']['warnings']
        total_info += p_audit['summary']['info']

    return {
        'project_id': project_id,
        'project_name': project.name,
        'total_pages': len(pages),
        'total_blocks': total_blocks,
        'total_issues': total_issues,
        'summary': {
            'errors': total_errors,
            'warnings': total_warnings,
            'info': total_info,
            'clean_pages': sum(1 for p in pages_audit if p['summary']['is_clean']),
            'pages_with_issues': sum(1 for p in pages_audit if not p['summary']['is_clean']),
        },
        'pages': pages_audit,
    }
