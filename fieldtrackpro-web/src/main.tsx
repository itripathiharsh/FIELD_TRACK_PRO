import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { ConfigErrorScreen } from './components/ui/ConfigErrorScreen'
import { ENV } from './config/env'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {ENV.CONFIG_ERRORS.length > 0 ? (
      <ConfigErrorScreen errors={ENV.CONFIG_ERRORS} />
    ) : (
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    )}
  </React.StrictMode>,
)
