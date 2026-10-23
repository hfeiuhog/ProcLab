"""Bounded authenticated speech transcription. Audio stays in memory, text is editable."""
import base64,io,wave
from pathlib import Path
import httpx
from .control import now

def transcribe_audio(settings,control,actor,filename,encoded):
    if '/' in filename or '\\' in filename:raise ValueError('音频文件名无效')
    try:content=base64.b64decode(encoded,validate=True)
    except ValueError:raise ValueError('音频编码无效') from None
    if not content or len(content)>4_000_000:raise ValueError('录音需小于4MB')
    suffix=Path(filename).suffix.lower()
    wav=content.startswith(b'RIFF') and content[8:12]==b'WAVE'
    valid=(wav and suffix=='.wav') or (content.startswith(b'\x1aE\xdf\xa3') and suffix=='.webm') or (content.startswith(b'OggS') and suffix=='.ogg') or (content[4:8]==b'ftyp' and suffix in ('.mp4','.m4a'))
    if not valid:raise ValueError('请选择WAV、WebM、Ogg或MP4录音')
    if wav:
        try:
            with wave.open(io.BytesIO(content)) as audio:
                if audio.getnframes()/audio.getframerate()>60:raise ValueError('每次录音最多60秒')
        except wave.Error:raise ValueError('WAV录音格式无效') from None
    if not settings.speech_enabled or not settings.siliconflow_api_key:raise RuntimeError('SpeechNotConfigured')
    control.consume('speech-user:'+actor+':'+now()[:10],20)
    control.consume('speech-global:'+now()[:10],100)
    mime={'.wav':'audio/wav','.webm':'audio/webm','.ogg':'audio/ogg','.mp4':'audio/mp4','.m4a':'audio/mp4'}[suffix]
    with httpx.Client(timeout=45,trust_env=False) as client:
        r=client.post(settings.siliconflow_base_url.rstrip('/')+'/audio/transcriptions',headers={'Authorization':'Bearer '+settings.siliconflow_api_key},
            data={'model':settings.speech_model},files={'file':(filename,content,mime)})
        r.raise_for_status();text=r.json().get('text','')
    if not isinstance(text,str) or not text.strip() or len(text)>12000:raise ValueError('未识别到有效语音，请重试')
    control.audit(actor,actor,'transcribe_audio','composer',{'bytes':len(content),'characters':len(text),'model':settings.speech_model,'audio_retained':False})
    return {'text':text.strip(),'model':settings.speech_model,'audio_retained':False}
