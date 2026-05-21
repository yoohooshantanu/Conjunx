"use client";

import React from "react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  componentName?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * React error boundary for wrapping components that may crash
 * (CesiumJS viewer, Canvas charts, etc).
 *
 * Shows a fallback UI instead of taking down the entire page.
 */
export default class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(
      `[ErrorBoundary] ${this.props.componentName || "Component"} crashed:`,
      error,
      info.componentStack
    );
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-col items-center justify-center min-h-[200px] bg-[#0d1117] border border-[#21262d] rounded p-6 text-center">
          <div className="text-[12px] text-[#f85149] font-data uppercase tracking-wider mb-2">
            Component Error
          </div>
          <div className="text-[11px] text-[#7d8590] max-w-md">
            {this.props.componentName || "This component"} encountered an error
            and could not render.
          </div>
          {this.state.error && (
            <div className="mt-3 text-[10px] text-[#484f58] font-data max-w-md break-all">
              {this.state.error.message}
            </div>
          )}
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 px-3 py-1.5 bg-[#161b22] border border-[#30363d] text-[11px] text-[#7d8590] hover:text-[#e6edf3] hover:bg-[#1c2128] transition-colors uppercase tracking-wider"
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
