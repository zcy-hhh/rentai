// 作者：zcy
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

// 全局错误边界：单个页面/组件渲染崩溃时不至于整个应用白屏
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 max-w-md text-center">
            <h2 className="font-semibold text-lg">页面出现异常</h2>
            <p className="text-sm text-gray-500 mt-2 break-all">
              {this.state.message}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, message: "" })}
              className="mt-4 px-4 py-2 bg-brand-600 text-white rounded-lg"
            >
              重试
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
