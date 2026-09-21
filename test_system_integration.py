import numpy as np
import json
from src.config import FRAME_RATE, EMOTIONS, EMOTION_POSITIVITY, MOUTH_SHAPE_CODES,PHONEME_MAP
# ============================================================================
# HANDCRAFTED TEST CRITERIA
# ============================================================================
# Scenario: "Yes! I am happy. But why?"
# Frame Expectations to Verify:
# 1. Punctuation Handling: "Yes!" should force a Pose rotation immediately.
# 2. Emotion Modulation: Character starts in 'explain' (0), shifts to 'happy' (1) 
#    at index 47, then drops to 'confused' (4) or 'rq' (5) at index 112.
# 3. Bilabial Sound Stops: The "m" in 'am' must force a closed mouth tracking shape.
mock_pipeline_words = [
    {
        "word": "yes", "start": 0.0, "end": 0.5,
        "phones": [{"phone": "y", "duration": 0.2}, {"phone": "eh", "duration": 0.2}, {"phone": "s", "duration": 0.1}]
    },
    {
        "word": "i", "start": 0.5, "end": 0.8,
        "phones": [{"phone": "ay", "duration": 0.3}]
    },
    {
        "word": "am", "start": 0.8, "end": 1.2,
        "phones": [{"phone": "ae", "duration": 0.2}, {"phone": "m", "duration": 0.2}] # Hard closed-mouth check
    },
    {
        "word": "happy", "start": 1.2, "end": 1.8,
        "phones": [{"phone": "hh", "duration": 0.1}, {"phone": "ae", "duration": 0.2}, {"phone": "p", "duration": 0.1}, {"phone": "iy", "duration": 0.2}]
    },
    {
        "word": "but", "start": 1.8, "end": 2.2,
        "phones": [{"phone": "b", "duration": 0.15}, {"phone": "ah", "duration": 0.15}, {"phone": "t", "duration": 0.1}]
    },
    {
        "word": "why", "start": 2.2, "end": 2.8,
        "phones": [{"phone": "w", "duration": 0.3}, {"phone": "ay", "duration": 0.3}]
    }
]

# Emulating the exact metadata output your script parser injects
mock_metadata_events = [
    {"emotion": "explain", "pos": 0},    # Start condition
    {"emotion": "happy", "pos": 5},      # Swaps at word "happy"
    {"emotion": "confused", "pos": 17}   # Swaps at word "why"
]

# ============================================================================
# SYSTEM INTEGRATION TEST SUITE
# ============================================================================
def run_integration_diagnostic():
    total_duration = 2.8
    total_frames = int(total_duration * FRAME_RATE)
    
    # --- MOCK SCHEDULER EXECUTION OUTPUT ---
    # In a production test, replace this section with your actual scheduler call:
    # final_mouths, final_poses, final_emotions = Scheduler.schedule_frames(...)
    

    final_mouths = np.zeros(total_frames, dtype=np.int32)
    final_poses = np.zeros(total_frames, dtype=np.int32)
    final_emotions = np.zeros(total_frames, dtype=np.int32)
    
    # Simulate step transitions
    current_pose = 0
    current_emotion = 0
    
    # Generate mock frame allocations matching your standard loops
    for i, w in enumerate(mock_pipeline_words):
        w_start = int(w["start"] * FRAME_RATE)
        w_end = int(w["end"] * FRAME_RATE)
        
        # Punctuation simulation: Rotation check on "Yes!" (Word index 0 completes)
        if i == 1: 
            current_pose = (current_pose + 2) % 5 
            
        # Emotion boundary triggers simulation
        if w["word"] == "happy": current_emotion = EMOTIONS["happy"]
        if w["word"] == "why": current_emotion = EMOTIONS["confused"]
            
        final_poses[w_start:w_end] = current_pose
        final_emotions[w_start:w_end] = current_emotion
        
        # Phone mapping loop
        t_cursor = w["start"]
        for p in w["phones"]:
            p_start = int(t_cursor * FRAME_RATE)
            p_end = int((t_cursor + p["duration"]) * FRAME_RATE)
            
            abstract_key = PHONEME_MAP.get(p["phone"], "m")
            abstract_id = MOUTH_SHAPE_CODES.get(abstract_key, 4)
            
            # Apply layout matrix row offsets directly to capture asset target changes
            is_pos = EMOTION_POSITIVITY[current_emotion] == 1
            offset = 1 if is_pos else 12
            
            final_mouths[p_start:p_end] = offset + abstract_id
            t_cursor += p["duration"]

    # ============================================================================
    # TIMELINE VALIDATION & ANALYSIS LAYER
    # ============================================================================
    print("=" * 95)
    print(" INTEGRATION MATRIX REPORT: PARSER METADATA -> TIMELINE ARRAYS")
    print("=" * 95)
    print(f"{'FRAME':<6} | {'TIME':<5} | {'ACTIVE WORD':<12} | {'EMOTION (ID)':<14} | {'POSE ID':<8} | {'TARGET ASSET':<14} | {'STATUS STATE'}")
    print("-" * 95)
    
    last_pose = final_poses[0]
    last_emo = final_emotions[0]
    
    rev_emotions = {v: k for k, v in EMOTIONS.items()}

    for f in range(total_frames):
        t_sec = f / FRAME_RATE
        
        # Identify active word contextual reference points
        active_word = "silence"
        for w in mock_pipeline_words:
            if w["start"] <= t_sec < w["end"]:
                active_word = w["word"].upper()
                break
                
        emo_id = final_emotions[f]
        emo_str = rev_emotions.get(emo_id, "unknown")
        pose_id = final_poses[f]
        mouth_asset = f"mouth{final_mouths[f]:04d}.png"
        
        # --- VERIFICATION ASSERTIONS ---
        status = "🟢 RUNNING"
        
        # A. Catch missing closed mouth structures for bilabial sounds
        if active_word == "AM" and t_sec >= 1.0: # Context bounds for phoneme [m]
            if final_mouths[f] != (1 + MOUTH_SHAPE_CODES["m"]) and final_mouths[f] != (12 + MOUTH_SHAPE_CODES["m"]):
                status = "❌ FAIL: [m] not closed"
                
        # B. Catch broken emotional baseline shifts
        if active_word == "HAPPY" and emo_str != "happy":
            status = "❌ FAIL: Emotion missed"
        if active_word == "WHY" and emo_str != "confused":
            status = "❌ FAIL: Emotion missed"
            
        # Highlight exact state transition boundaries directly inline
        if pose_id != last_pose:
            status = f"🔄 POSE SHIFT: {last_pose} -> {pose_id}"
            last_pose = pose_id
        if emo_id != last_emo:
            status = f"🎭 EMO SHIFT: {rev_emotions.get(last_emo).upper()} -> {emo_str.upper()}"
            last_emo = emo_id

        print(f"{f:<6} | {t_sec:<5.2f} | {active_word:<12} | {emo_str:<9} ({emo_id}) | {pose_id:<8} | {mouth_asset:<14} | {status}")

if __name__ == "__main__":
    run_integration_diagnostic()