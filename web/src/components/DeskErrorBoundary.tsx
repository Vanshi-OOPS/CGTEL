import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

export class DeskErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Execution Desk render failed', error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return (
        <section role="alert" className="desk-render-error">
          <h2>The Execution Desk could not render this run.</h2>
          <p>Reload the page to restore the workspace.</p>
          <button type="button" onClick={() => window.location.reload()}>Reload</button>
        </section>
      );
    }
    return this.props.children;
  }
}
