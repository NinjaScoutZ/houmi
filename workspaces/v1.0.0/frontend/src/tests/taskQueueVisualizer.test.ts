// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react';
import {
  TaskQueueVisualizer,
  emitPipelineTask,
  type PipelineTask,
} from '../components/TaskQueueVisualizer';

describe('TaskQueueVisualizer Component Tests', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('exports TaskQueueVisualizer component and emitPipelineTask helper', () => {
    expect(TaskQueueVisualizer).toBeDefined();
    expect(emitPipelineTask).toBeTypeOf('function');
  });

  it('renders null when there are no active tasks', () => {
    const { container } = render(
      React.createElement(TaskQueueVisualizer, { lastMessage: null, projectId: 'proj-123' })
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('task-queue-visualizer')).toBeNull();
  });

  it('accepts controlled external tasks array and renders DOM task cards and progress bars', () => {
    const sampleTasks: PipelineTask[] = [
      {
        id: 'task-1',
        type: 'ocr',
        title: 'OCR Text Recognition',
        stage: 'Running OCR Recognition',
        currentItem: 'Page 3 of 10',
        progress: 45,
        status: 'running',
        timestamp: Date.now(),
      },
      {
        id: 'task-2',
        type: 'inpainting',
        title: 'Inpainting / Cleaning',
        stage: 'Cleaning Background',
        currentItem: 'Page 3 of 10',
        progress: 100,
        status: 'completed',
        timestamp: Date.now(),
      },
    ];

    render(React.createElement(TaskQueueVisualizer, { tasks: sampleTasks, projectId: 'proj-123' }));

    expect(screen.getByTestId('task-queue-visualizer')).not.toBeNull();
    expect(screen.getByTestId('task-card-task-1')).not.toBeNull();
    expect(screen.getByTestId('task-card-task-2')).not.toBeNull();

    expect(screen.getByText('OCR Text Recognition')).not.toBeNull();
    expect(screen.getByText('Inpainting / Cleaning')).not.toBeNull();
    expect(screen.getByText('RUNNING')).not.toBeNull();
    expect(screen.getByText('DONE')).not.toBeNull();

    const progressBar1 = screen.getByTestId('progress-bar-task-1');
    expect(progressBar1.style.width).toBe('45%');

    const progressBar2 = screen.getByTestId('progress-bar-task-2');
    expect(progressBar2.style.width).toBe('100%');
  });

  it('formats batch_progress WebSocket messages into active pipeline task DOM items', () => {
    const wsMessage = {
      type: 'batch_progress',
      status: 'running',
      progress: 0.65,
      current_page: 4,
      total_pages: 12,
      step: 'inpaint',
    };

    render(
      React.createElement(TaskQueueVisualizer, { lastMessage: wsMessage, projectId: 'proj-456' })
    );

    expect(screen.getByTestId('task-queue-visualizer')).not.toBeNull();
    expect(screen.getByText('Inpainting / Cleaning')).not.toBeNull();
    expect(screen.getByText('Cleaning Text Backgrounds')).not.toBeNull();
    expect(screen.getByText('Page 4 of 12')).not.toBeNull();

    const progressBar = screen.getByTestId('progress-bar-batch_proj-456');
    expect(progressBar.style.width).toBe('65%');
  });

  it('formats page_progress WebSocket messages for single-page pipeline steps into DOM', () => {
    const wsMessage = {
      type: 'page_progress',
      status: 'running',
      step: 'ocr',
      page_id: 'page_999',
      progress: 0.8,
    };

    render(
      React.createElement(TaskQueueVisualizer, { lastMessage: wsMessage, projectId: 'proj-789' })
    );

    expect(screen.getByTestId('task-queue-visualizer')).not.toBeNull();
    expect(screen.getByText('OCR Task')).not.toBeNull();
    expect(screen.getByText('Running OCR')).not.toBeNull();
    expect(screen.getByText('Page page_999')).not.toBeNull();

    const progressBar = screen.getByTestId('progress-bar-page_page_999');
    expect(progressBar.style.width).toBe('80%');
  });

  it('dispatches custom pipeline task events via emitPipelineTask and renders task card', () => {
    render(React.createElement(TaskQueueVisualizer));

    act(() => {
      emitPipelineTask({
        id: 'custom-task-1',
        type: 'translation',
        title: 'AI Translation',
        stage: 'Translating Content',
        currentItem: 'Page 1',
        progress: 30,
        status: 'running',
      });
    });

    expect(screen.getByTestId('task-card-custom-task-1')).not.toBeNull();
    expect(screen.getByText('AI Translation')).not.toBeNull();
    expect(screen.getByText('Translating Content')).not.toBeNull();
    expect(screen.getByText('Page 1')).not.toBeNull();

    const progressBar = screen.getByTestId('progress-bar-custom-task-1');
    expect(progressBar.style.width).toBe('30%');
  });

  it('handles failed status and error message display in DOM elements', () => {
    const failedTask: PipelineTask = {
      id: 'failed-ocr-1',
      type: 'ocr',
      title: 'OCR Recognition',
      stage: 'Failed during OCR',
      currentItem: 'Page 5',
      progress: 50,
      status: 'failed',
      error: 'CUDA Out of Memory',
      timestamp: Date.now(),
    };

    render(React.createElement(TaskQueueVisualizer, { tasks: [failedTask] }));

    expect(screen.getByTestId('task-card-failed-ocr-1')).not.toBeNull();
    expect(screen.getByText('FAILED')).not.toBeNull();
    expect(screen.getByText('CUDA Out of Memory')).not.toBeNull();
    expect(screen.getByTestId('dismiss-btn-failed-ocr-1')).not.toBeNull();

    const progressBar = screen.getByTestId('progress-bar-failed-ocr-1');
    expect(progressBar.style.width).toBe('50%');
  });

  it('toggles expand and collapse state when toggle button is clicked', () => {
    const sampleTasks: PipelineTask[] = [
      {
        id: 'task-toggle-1',
        type: 'ocr',
        title: 'OCR Test Task',
        stage: 'Testing Stage',
        progress: 50,
        status: 'running',
        timestamp: Date.now(),
      },
    ];

    render(React.createElement(TaskQueueVisualizer, { tasks: sampleTasks, initialExpanded: true }));

    expect(screen.getByTestId('task-card-task-toggle-1')).not.toBeNull();

    const toggleBtn = screen.getByTestId('toggle-expand-btn');
    fireEvent.click(toggleBtn);

    expect(screen.queryByTestId('task-card-task-toggle-1')).toBeNull();

    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('task-card-task-toggle-1')).not.toBeNull();
  });

  it('allows manual task dismissal and clearing completed tasks from DOM', () => {
    const onTasksChange = vi.fn();
    const sampleTasks: PipelineTask[] = [
      {
        id: 'running-task',
        type: 'ocr',
        title: 'Running Task',
        stage: 'Running',
        progress: 20,
        status: 'running',
        timestamp: Date.now(),
      },
      {
        id: 'completed-task',
        type: 'render',
        title: 'Completed Task',
        stage: 'Done',
        progress: 100,
        status: 'completed',
        timestamp: Date.now(),
      },
    ];

    render(React.createElement(TaskQueueVisualizer, { tasks: sampleTasks, onTasksChange }));

    const dismissBtn = screen.getByTestId('dismiss-btn-completed-task');
    fireEvent.click(dismissBtn);

    expect(onTasksChange).toHaveBeenCalled();
  });

  it('auto-dismisses completed tasks after timer elapses', () => {
    const wsMessage = {
      type: 'page_progress',
      status: 'success',
      step: 'ocr',
      page_id: 'auto_dismiss_page',
    };

    render(React.createElement(TaskQueueVisualizer, { lastMessage: wsMessage }));

    expect(screen.getByTestId('task-card-page_auto_dismiss_page')).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(4000);
    });

    expect(screen.queryByTestId('task-card-page_auto_dismiss_page')).toBeNull();
  });
});
