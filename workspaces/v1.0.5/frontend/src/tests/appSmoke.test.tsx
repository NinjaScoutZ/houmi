// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import React from 'react';
import { render } from '@testing-library/react';
import { App } from '../App';

describe('App Smoke Test', () => {
  it('mounts without TDZ / ReferenceError', () => {
    // Mock HTMLCanvasElement
    HTMLCanvasElement.prototype.getContext = () => null;
    const { container } = render(<App />);
    expect(container).toBeDefined();
  });
});
