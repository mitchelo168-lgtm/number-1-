import './App.css'
import { ClipReviewQueue } from './components/ClipReviewQueue'
import { CredentialStatus } from './components/CredentialStatus'
import { StreamerManager } from './components/StreamerManager'

function App() {
  return (
    <div className="app">
      <header>
        <h1>streamclip</h1>
      </header>
      <main>
        <div className="column">
          <StreamerManager />
          <CredentialStatus />
        </div>
        <div className="column">
          <ClipReviewQueue />
        </div>
      </main>
    </div>
  )
}

export default App
