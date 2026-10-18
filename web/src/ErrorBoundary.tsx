// Keeps one broken component from blanking the whole app: React unmounts
// everything above an uncaught render error unless a boundary catches it.
import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** shown instead of the children after an error (default: nothing) */
  fallback?: ReactNode;
  onError?: (error: Error) => void;
}

export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    console.error(error);
    this.props.onError?.(error);
  }

  render() {
    return this.state.failed ? (this.props.fallback ?? null) : this.props.children;
  }
}

/** Whole-app fallback, in both languages since strings may be what broke. */
export const AppCrashed = () => (
  <div className="app-crashed" role="alert">
    <p>Terjadi kesalahan. / Something went wrong.</p>
    <button onClick={() => window.location.reload()}>Muat ulang / Reload</button>
  </div>
);
