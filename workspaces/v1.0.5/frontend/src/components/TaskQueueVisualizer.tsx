import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Trash2,
  Loader2,
  Sparkles,
  Layers,
  Paintbrush,
  Globe,
  X,
} from 'lucide-react';

export type PipelineTaskType =
  | 'ocr'
  | 'inpainting'
  | 'cleaning'
  | 'render'
  | 'psd'
  | 'translation'
  | 'pipeline'
  | 'batch';

export type PipelineTaskStatus = 'running' | 'completed' | 'failed' | 'cancelled';

export interface PipelineTask {
  id: string;
  type: PipelineTaskType;
  title: string;
  stage: string;
  currentItem?: string;
  progress: number; // 0 - 100
  status: PipelineTaskStatus;
  error?: string | null;
  timestamp: number;
  autoDismissMs?: number;
}

export interface TaskQueueVisualizerProps {
  /** Real-time WebSocket message object from useWebSocket hook */
  lastMessage?: { type: string; [key: string]: any } | null;
  /** Active project ID */
  projectId?: string | null;
  /** Optional external tasks array for controlled usage */
  tasks?: PipelineTask[];
  /** Callback when tasks change */
  onTasksChange?: (tasks: PipelineTask[]) => void;
  /** Custom wrapper CSS class */
  className?: string;
  /** Initial collapse state */
  initialExpanded?: boolean;
}

/** Helper function to programmatically dispatch a pipeline task event from anywhere in the frontend */
export function emitPipelineTask(task: Omit<PipelineTask, 'timestamp'> & { timestamp?: number }) {
  const fullTask: PipelineTask = {
    ...task,
    timestamp: task.timestamp || Date.now(),
  };
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    window.dispatchEvent(
      new CustomEvent('houmi-pipeline-task', { detail: fullTask })
    );
  }
}

const DEFAULT_DISMISS_MS = 4000;

export const TaskQueueVisualizer: React.FC<TaskQueueVisualizerProps> = ({
  lastMessage,
  projectId,
  tasks: externalTasks,
  onTasksChange,
  className = '',
  initialExpanded = true,
}) => {
  const [internalTasks, setInternalTasks] = useState<PipelineTask[]>([]);
  const [isExpanded, setIsExpanded] = useState(initialExpanded);
  const lastProcessedWSMessageRef = useRef<any>(null);
  const dismissTimerMapRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // Effective tasks list (use external if provided, otherwise internal)
  const activeTasks = externalTasks || internalTasks;

  const updateTasksState = useCallback(
    (updater: (prev: PipelineTask[]) => PipelineTask[]) => {
      setInternalTasks((prev) => {
        const next = updater(prev);
        if (onTasksChange) {
          onTasksChange(next);
        }
        return next;
      });
    },
    [onTasksChange]
  );

  // Helper to schedule auto-dismissal of completed or failed tasks
  const scheduleAutoDismiss = useCallback(
    (taskId: string, dismissMs: number = DEFAULT_DISMISS_MS) => {
      if (dismissTimerMapRef.current.has(taskId)) {
        clearTimeout(dismissTimerMapRef.current.get(taskId)!);
      }
      const timer = setTimeout(() => {
        updateTasksState((prev) => prev.filter((t) => t.id !== taskId));
        dismissTimerMapRef.current.delete(taskId);
      }, dismissMs);
      dismissTimerMapRef.current.set(taskId, timer);
    },
    [updateTasksState]
  );

  // Handle incoming WebSocket messages
  useEffect(() => {
    if (!lastMessage || lastProcessedWSMessageRef.current === lastMessage) return;
    lastProcessedWSMessageRef.current = lastMessage;

    const messageType = lastMessage.type;

    if (messageType === 'batch_progress') {
      const {
        status,
        progress,
        current_page,
        total_pages,
        step,
        error,
        completed_blocks,
        total_blocks,
        batch_index,
        total_batches,
        batch_size,
      } = lastMessage;

      const rawProgress = typeof progress === 'number' ? progress : 0;
      const progressPercent = Math.min(100, Math.max(0, Math.round(rawProgress * 100)));

      let mappedType: PipelineTaskType = 'batch';
      let mappedTitle = 'Batch Pipeline Task';
      let mappedStage = 'Processing batch...';

      if (step === 'detect') {
        mappedType = 'ocr';
        mappedTitle = 'OCR & Bubble Detection';
        mappedStage = 'Detecting Speech Balloons';
      } else if (step === 'ocr') {
        mappedType = 'ocr';
        mappedTitle = 'OCR Text Recognition';
        mappedStage = 'Running OCR Recognition';
        if (typeof total_blocks === 'number' && total_blocks > 0) {
          const batchLabel = typeof total_batches === 'number' && total_batches > 0
            ? ` · Batch ${batch_index || 1}/${total_batches} (${batch_size || 1}/request)`
            : '';
          mappedStage = `OCR ${completed_blocks || 0}/${total_blocks} boxes${batchLabel}`;
        }
      } else if (step === 'layout') {
        mappedType = 'translation';
        mappedTitle = 'Layout Analysis';
        mappedStage = 'Analyzing Page Layout';
      } else if (step === 'sort') {
        mappedType = 'translation';
        mappedTitle = 'Reading Order';
        mappedStage = 'Sorting Reading Order';
      } else if (step === 'inpaint' || step === 'clean') {
        mappedType = 'inpainting';
        mappedTitle = 'Inpainting / Cleaning';
        mappedStage = 'Cleaning Text Backgrounds';
      } else if (step === 'render' || step === 'psd') {
        mappedType = 'render';
        mappedTitle = 'PSD & Canvas Rendering';
        mappedStage = 'Rendering PSD Text Layers';
      } else if (step === 'translate') {
        mappedType = 'translation';
        mappedTitle = 'AI Translation';
        mappedStage = 'Translating Text Content';
      } else if (step === 'done') {
        mappedStage = 'Batch Tasks Complete';
      } else if (step) {
        mappedStage = `Step: ${step}`;
      }

      const itemDisplay = total_pages
        ? `Page ${current_page || 0} of ${total_pages}${typeof total_blocks === 'number' && total_blocks > 0 ? ` · ${completed_blocks || 0}/${total_blocks} boxes` : ''}`
        : current_page
        ? `Page ${current_page}`
        : 'All Pages';

      const taskStatus: PipelineTaskStatus =
        status === 'running'
          ? 'running'
          : status === 'success'
          ? 'completed'
          : status === 'failed'
          ? 'failed'
          : 'cancelled';

      const taskId = `batch_${projectId || 'default'}`;

      updateTasksState((prev) => {
        const existingIdx = prev.findIndex((t) => t.id === taskId);
        const newTask: PipelineTask = {
          id: taskId,
          type: mappedType,
          title: mappedTitle,
          stage: mappedStage,
          currentItem: itemDisplay,
          progress: progressPercent,
          status: taskStatus,
          error: error || null,
          timestamp: Date.now(),
        };

        if (existingIdx >= 0) {
          const updated = [...prev];
          updated[existingIdx] = newTask;
          return updated;
        } else {
          return [newTask, ...prev];
        }
      });

      // Auto popup visualizer on active running task
      if (taskStatus === 'running') {
        setIsExpanded(true);
      } else if (taskStatus === 'completed' || taskStatus === 'failed') {
        scheduleAutoDismiss(taskId);
      }
    } else if (messageType === 'page_progress') {
      const { status, step, page_id, error, progress } = lastMessage;

      let mappedType: PipelineTaskType = 'pipeline';
      let mappedTitle = 'Page Pipeline Task';
      let mappedStage = 'Processing page...';

      if (step === 'detect' || step === 'ocr') {
        mappedType = 'ocr';
        mappedTitle = 'OCR Task';
        mappedStage = step === 'ocr' ? 'Running OCR' : 'Detecting Text';
      } else if (step === 'inpaint' || step === 'clean') {
        mappedType = 'inpainting';
        mappedTitle = 'Inpainting Task';
        mappedStage = 'Cleaning Image Background';
      } else if (step === 'render' || step === 'psd') {
        mappedType = 'render';
        mappedTitle = 'PSD Render Task';
        mappedStage = 'Rendering Page Canvas';
      } else if (step === 'translate') {
        mappedType = 'translation';
        mappedTitle = 'Translation Task';
        mappedStage = 'Translating Page Text';
      } else if (step) {
        mappedStage = `Step: ${step}`;
      }

      const taskStatus: PipelineTaskStatus =
        status === 'running'
          ? 'running'
          : status === 'success'
          ? 'completed'
          : 'failed';

      const progressPercent =
        taskStatus === 'completed'
          ? 100
          : taskStatus === 'failed'
          ? 100
          : typeof progress === 'number'
          ? Math.round(progress * 100)
          : 50;

      const taskId = `page_${page_id || step || 'task'}`;
      const itemDisplay = page_id ? `Page ${page_id}` : 'Current Page';

      updateTasksState((prev) => {
        const existingIdx = prev.findIndex((t) => t.id === taskId);
        const newTask: PipelineTask = {
          id: taskId,
          type: mappedType,
          title: mappedTitle,
          stage: mappedStage,
          currentItem: itemDisplay,
          progress: progressPercent,
          status: taskStatus,
          error: error || null,
          timestamp: Date.now(),
        };

        if (existingIdx >= 0) {
          const updated = [...prev];
          updated[existingIdx] = newTask;
          return updated;
        } else {
          return [newTask, ...prev];
        }
      });

      if (taskStatus === 'running') {
        setIsExpanded(true);
      } else if (taskStatus === 'completed' || taskStatus === 'failed') {
        scheduleAutoDismiss(taskId);
      }
    } else if (messageType === 'task_progress' || messageType === 'pipeline_task') {
      const { id, type, title, stage, currentItem, progress, status, error } = lastMessage;
      if (id) {
        const progressPercent = Math.min(100, Math.max(0, Math.round(progress ?? 0)));
        const taskStatus: PipelineTaskStatus = status || 'running';
        const newTask: PipelineTask = {
          id,
          type: (type as PipelineTaskType) || 'pipeline',
          title: title || 'Background Task',
          stage: stage || 'Processing...',
          currentItem: currentItem || '',
          progress: progressPercent,
          status: taskStatus,
          error: error || null,
          timestamp: Date.now(),
        };

        updateTasksState((prev) => {
          const existingIdx = prev.findIndex((t) => t.id === id);
          if (existingIdx >= 0) {
            const updated = [...prev];
            updated[existingIdx] = newTask;
            return updated;
          } else {
            return [newTask, ...prev];
          }
        });

        if (taskStatus === 'running') {
          setIsExpanded(true);
        } else if (taskStatus === 'completed' || taskStatus === 'failed') {
          scheduleAutoDismiss(id);
        }
      }
    }
  }, [lastMessage, projectId, updateTasksState, scheduleAutoDismiss]);

  // Listen for custom window events dispatched via emitPipelineTask
  useEffect(() => {
    const handleCustomTaskEvent = (e: Event) => {
      const customEvent = e as CustomEvent<PipelineTask>;
      if (!customEvent.detail || !customEvent.detail.id) return;
      const task = customEvent.detail;

      updateTasksState((prev) => {
        const existingIdx = prev.findIndex((t) => t.id === task.id);
        if (existingIdx >= 0) {
          const updated = [...prev];
          updated[existingIdx] = task;
          return updated;
        } else {
          return [task, ...prev];
        }
      });

      if (task.status === 'running') {
        setIsExpanded(true);
      } else if (task.status === 'completed' || task.status === 'failed') {
        scheduleAutoDismiss(task.id, task.autoDismissMs || DEFAULT_DISMISS_MS);
      }
    };

    if (typeof window !== 'undefined' && window.addEventListener) {
      window.addEventListener('houmi-pipeline-task', handleCustomTaskEvent);
      return () => {
        window.removeEventListener('houmi-pipeline-task', handleCustomTaskEvent);
      };
    }
  }, [updateTasksState, scheduleAutoDismiss]);

  // Clean up timers on unmount
  useEffect(() => {
    return () => {
      dismissTimerMapRef.current.forEach((timer) => clearTimeout(timer));
      dismissTimerMapRef.current.clear();
    };
  }, []);

  const handleDismissTask = (taskId: string) => {
    if (dismissTimerMapRef.current.has(taskId)) {
      clearTimeout(dismissTimerMapRef.current.get(taskId)!);
      dismissTimerMapRef.current.delete(taskId);
    }
    updateTasksState((prev) => prev.filter((t) => t.id !== taskId));
  };

  const handleClearCompleted = () => {
    updateTasksState((prev) => prev.filter((t) => t.status === 'running'));
  };

  if (activeTasks.length === 0) {
    return null;
  }

  const runningCount = activeTasks.filter((t) => t.status === 'running').length;
  const hasCompleted = activeTasks.some((t) => t.status === 'completed' || t.status === 'failed');

  const getTaskIcon = (type: PipelineTaskType) => {
    switch (type) {
      case 'ocr':
        return <Sparkles className="w-4 h-4 text-amber-400" />;
      case 'inpainting':
      case 'cleaning':
        return <Paintbrush className="w-4 h-4 text-cyan-400" />;
      case 'render':
      case 'psd':
        return <Layers className="w-4 h-4 text-purple-400" />;
      case 'translation':
        return <Globe className="w-4 h-4 text-emerald-400" />;
      case 'batch':
      case 'pipeline':
      default:
        return <Activity className="w-4 h-4 text-orange-400" />;
    }
  };

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex flex-col items-end max-w-sm w-80 sm:w-96 font-sans transition-all duration-300 ${className}`}
      data-testid="task-queue-visualizer"
    >
      {/* Toast Visualizer Header Bar */}
      <div className="w-full bg-slate-900/95 border border-slate-700/80 rounded-xl shadow-2xl backdrop-blur-md overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-3.5 py-2.5 bg-slate-800/90 border-b border-slate-700/60">
          <div className="flex items-center gap-2">
            {runningCount > 0 ? (
              <Loader2 className="w-4 h-4 text-orange-400 animate-spin" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            )}
            <span className="text-xs font-bold text-slate-100 tracking-wide font-pixel">
              Task Queue Visualizer
            </span>
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-orange-500/20 text-orange-300 border border-orange-500/30">
              {runningCount > 0 ? `${runningCount} active` : `${activeTasks.length} done`}
            </span>
          </div>

          <div className="flex items-center gap-1">
            {hasCompleted && (
              <button
                onClick={handleClearCompleted}
                className="p-1 text-slate-400 hover:text-slate-200 transition-colors rounded hover:bg-slate-700/50"
                title="Clear completed tasks"
                data-testid="clear-completed-btn"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              onClick={() => setIsExpanded((prev) => !prev)}
              className="p-1 text-slate-400 hover:text-slate-200 transition-colors rounded hover:bg-slate-700/50"
              title={isExpanded ? 'Collapse' : 'Expand'}
              data-testid="toggle-expand-btn"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronUp className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        {/* Task Cards Container */}
        {isExpanded && (
          <div className="p-3 max-h-80 overflow-y-auto space-y-2.5 divide-y divide-slate-800/60">
            {activeTasks.map((task) => {
              const isRunning = task.status === 'running';
              const isSuccess = task.status === 'completed';
              const isFailed = task.status === 'failed';

              return (
                <div
                  key={task.id}
                  className="pt-2.5 first:pt-0 flex flex-col gap-1.5 group"
                  data-testid={`task-card-${task.id}`}
                >
                  {/* Title & Actions Row */}
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="shrink-0">{getTaskIcon(task.type)}</div>
                      <div className="truncate font-semibold text-slate-200">
                        {task.title}
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <span
                        className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                          isRunning
                            ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                            : isSuccess
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                            : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                        }`}
                      >
                        {isRunning ? 'RUNNING' : isSuccess ? 'DONE' : 'FAILED'}
                      </span>

                      {!isRunning && (
                        <button
                          onClick={() => handleDismissTask(task.id)}
                          className="text-slate-500 hover:text-slate-300 p-0.5 rounded transition-colors"
                          title="Dismiss task"
                          data-testid={`dismiss-btn-${task.id}`}
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Stage and Current Item Info */}
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span className="truncate text-slate-300 font-medium">
                      {task.stage}
                    </span>
                    {task.currentItem && (
                      <span className="font-mono text-[10px] text-amber-300/80 bg-amber-500/10 px-1.5 py-0.5 rounded shrink-0 ml-2">
                        {task.currentItem}
                      </span>
                    )}
                  </div>

                  {/* Progress Bar & Percentage */}
                  <div className="flex items-center gap-2 mt-0.5">
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden border border-slate-700/50 p-0.5">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${
                          isFailed
                            ? 'bg-rose-500'
                            : isSuccess
                            ? 'bg-emerald-400'
                            : 'bg-gradient-to-r from-orange-500 via-amber-400 to-amber-300 animate-pulse'
                        }`}
                        style={{ width: `${task.progress}%` }}
                        data-testid={`progress-bar-${task.id}`}
                      />
                    </div>
                    <span className="text-[11px] font-mono font-bold text-slate-200 min-w-[32px] text-right">
                      {task.progress}%
                    </span>
                  </div>

                  {/* Error Message if failed */}
                  {task.error && (
                    <div className="text-[10px] text-rose-300 bg-rose-950/60 border border-rose-500/30 rounded p-1.5 mt-1 flex items-start gap-1">
                      <AlertCircle className="w-3 h-3 text-rose-400 shrink-0 mt-0.5" />
                      <span className="break-words leading-tight">{task.error}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
