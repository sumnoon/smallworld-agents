"""Assemble synthetic narration and a quiet original procedural score."""
import json
import wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
RATE=48000
scenes=json.loads((ROOT/'tools/video/storyboard.json').read_text(encoding='utf-8'))
clock=0
clips=[]
for scene in scenes:
    with wave.open(str(ROOT/'.video-build'/f"{scene['id']}.wav")) as source:
        assert source.getsampwidth()==2
        samples=np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').astype(np.float64)/32768
        samples=samples.reshape(-1,source.getnchannels()).mean(axis=1)
        duration=len(samples)/source.getframerate()
        samples=np.interp(np.arange(round(duration*RATE))/RATE,np.arange(len(samples))/source.getframerate(),samples)
    scene.update(start=round(clock,3),duration=round(max(scene['min_seconds'],duration+1.0),3))
    scene['end']=round(scene['start']+scene['duration'],3)
    clips.append((round((clock+.35)*RATE),samples))
    clock=scene['end']
track=np.zeros(round(clock*RATE))
for offset,samples in clips:
    track[offset:offset+len(samples)]+=samples*.8
# Soft plucked C/Am/F/G arpeggios authored for this introduction.
chords=[[48,55,60,64],[45,52,57,60],[41,48,53,57],[43,50,55,59]]
for n,start in enumerate(np.arange(0,clock,.75)):
    midi=chords[(n//8)%4][n%4]+12
    freq=440*2**((midi-69)/12)
    t=np.arange(int(2.8*RATE))/RATE
    tone=(np.sin(2*np.pi*freq*t)+.3*np.sin(2*np.pi*2*freq*t)+.08*np.sin(2*np.pi*3*freq*t))
    tone*=.012*np.exp(-2.2*t)*np.minimum(t/.02,1)
    offset=round(start*RATE)
    length=min(len(tone),len(track)-offset)
    track[offset:offset+length]+=tone[:length]
fade=np.minimum(np.arange(len(track))/RATE/1.5,(len(track)-np.arange(len(track)))/RATE/1.5)
track*=np.clip(fade,0,1)
track=np.clip(track,-.96,.96)
with wave.open(str(ROOT/'.video-build/mix.wav'),'wb') as output:
    output.setnchannels(1);output.setsampwidth(2);output.setframerate(RATE)
    output.writeframes((track*32767).astype('<i2').tobytes())
(ROOT/'.video-build/timeline.json').write_text(json.dumps(scenes,indent=2,ensure_ascii=False),encoding='utf-8')
print('Narrated duration:',round(clock,2),'seconds')
