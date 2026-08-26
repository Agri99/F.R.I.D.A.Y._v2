"""Voice session management."""
from __future__ import annotations
from enum import Enum
from typing import Any

class SessionState(Enum):
    """Possible states for a voice interaction session."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    FOLLOWUP = "followup"

class VoiceSession:
    """Manages the state and flow of a voice interaction session."""
    
    def __init__(self, stt: Any, tts: Any, wakeword: Any):
        self.stt = stt
        self.tts = tts
        self.wakeword = wakeword
        self.state = SessionState.IDLE
        self.is_cancelled = False
        
    def set_state(self, new_state: SessionState) -> None:
        """Update the session state."""
        self.state = new_state
        print(f"Session State: {self.state.value}")
        
    def cancel(self) -> None:
        """Cancel the ongoing session."""
        self.is_cancelled = True
        self.set_state(SessionState.IDLE)
        
    def run_loop(self) -> None:
        """Run the main interaction loop (wake -> listen -> process -> speak)."""
        while True:
            self.set_state(SessionState.IDLE)
            self.wakeword.listen_for_wakeword()
            
            if self.is_cancelled:
                self.is_cancelled = False
                continue
                
            self.set_state(SessionState.LISTENING)
            audio_path = self.stt.record_until_silence()
            
            self.set_state(SessionState.PROCESSING)
            text = self.stt.transcribe(audio_path)
            print(f"User: {text}")
            
            # Agent processing would go here
            response_text = "I heard you say: " + text
            
            self.set_state(SessionState.SPEAKING)
            interrupted = self.tts.speak_interruptible(response_text, self.wakeword)
            
            if interrupted:
                print("Speech interrupted by wake word!")
                continue
                
            self.set_state(SessionState.FOLLOWUP)
            followup_path = self.stt.listen_for_followup(timeout_seconds=5.0)
            if followup_path:
                print("Follow up detected.")
                # Can loop back to processing here
