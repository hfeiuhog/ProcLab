"use strict";
let voiceSession=null,voiceSequence=0;

function syncVoiceControls(){
  const session=voiceSession,active=!!session,recording=session?.phase==='recording';
  $('composer').classList.toggle('is-dictating',active);
  $('voice-status').hidden=!active;
  $('voice-status').classList.toggle('recording',recording);
  $('voice-status').classList.toggle('transcribing',session?.phase==='transcribing');
  $('voice-input').hidden=active;
  $('voice-input').disabled=sending||active;
  $('question').readOnly=active;
  $('send').disabled=sending||(active&&!recording);
  $('send').title=recording?'停止听写并发送':sending?'任务执行中':'发送';
  $('send').setAttribute('aria-label',recording?'停止听写并发送':sending?'任务执行中':'发送分析任务');
  $('voice-stop').hidden=!recording;
  if(active){
    $('voice-message').textContent=recording?'正在听写':session.phase==='transcribing'?(session.sendAfter?'正在转写并发送…':'正在转成文字…'):'等待麦克风授权…';
    $('voice-waveform').toggleAttribute('hidden',!recording);
    $('voice-time').hidden=!recording;
  }
}
function releaseMicrophone(session){
  if(!session)return;
  clearTimeout(session.timer);clearInterval(session.clock);cancelAnimationFrame(session.frame);
  session.source?.disconnect();session.source=null;
  if(session.audioContext){const context=session.audioContext;session.audioContext=null;if(context.state!=='closed')context.close().catch(()=>{});}
  session.stream?.getTracks().forEach(track=>track.stop());
}
function cancelVoice(focus=false){
  voiceSequence++;
  const session=voiceSession;voiceSession=null;
  if(session){
    session.cancelled=true;session.controller.abort();
    if(session.recorder?.state==='recording')session.recorder.stop();
    releaseMicrophone(session);session.parts=[];
  }
  syncVoiceControls();
  if(focus)$('question').focus();
}
function updateVoiceTime(session){
  const seconds=Math.min(60,Math.floor((Date.now()-session.started)/1000));
  $('voice-time').textContent='0:'+String(seconds).padStart(2,'0')+' / 1:00';
}
function startVoiceWaveform(session){
  const AudioContext=window.AudioContext||window.webkitAudioContext;
  if(!AudioContext)return;
  try{
    session.audioContext=new AudioContext();
    session.source=session.audioContext.createMediaStreamSource(session.stream);
    const analyser=session.audioContext.createAnalyser();analyser.fftSize=256;
    session.source.connect(analyser);
    // Analyse the microphone without playing it through the speakers.
    session.audioContext.resume().catch(()=>{});
    const samples=new Float32Array(analyser.fftSize),levels=Array(48).fill(0);
    const draw=now=>{
      if(voiceSession!==session||session.phase!=='recording')return;
      if(!session.lastFrame||now-session.lastFrame>=60){
        session.lastFrame=now;analyser.getFloatTimeDomainData(samples);
        const rms=Math.sqrt(samples.reduce((sum,n)=>sum+n*n,0)/samples.length);
        levels.push(Math.min(1,rms*6));levels.shift();
        $('voice-wave-path').setAttribute('d',levels.map((level,i)=>{
          const half=1+level*17,x=2+i*5;return 'M'+x+','+(20-half).toFixed(1)+'v'+(half*2).toFixed(1);
        }).join(' '));
      }
      session.frame=requestAnimationFrame(draw);
    };
    session.frame=requestAnimationFrame(draw);
  }catch{
    // Recording still works if this browser cannot visualise microphone input.
    session.source?.disconnect();session.source=null;
    if(session.audioContext){session.audioContext.close().catch(()=>{});session.audioContext=null;}
  }
}
async function startVoice(){
  if(voiceSession||sending)return;
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){toast('当前浏览器不能录音，请使用最新版 Chrome 或 Edge，并通过 HTTPS 打开。');return;}
  closeComposerMenus();
  const session={sequence:++voiceSequence,phase:'requesting',controller:new AbortController(),parts:[],cancelled:false,sendAfter:false};
  voiceSession=session;
  $('voice-wave-path').setAttribute('d','M0 20H240');$('voice-time').textContent='0:00 / 1:00';
  syncVoiceControls();$('voice-cancel').focus();
  try{
    session.stream=await navigator.mediaDevices.getUserMedia({audio:true});
    if(session.cancelled||voiceSession!==session){releaseMicrophone(session);return;}
    const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
    if(!mime)throw Error('当前浏览器不支持录音格式，请更换 Chrome 或 Edge。');
    session.mime=mime;session.recorder=new MediaRecorder(session.stream,{mimeType:mime,audioBitsPerSecond:64000});
    session.recorder.ondataavailable=e=>{if(!session.cancelled&&e.data.size)session.parts.push(e.data);};
    session.recorder.onstop=()=>finishVoice(session);
    session.recorder.onerror=()=>{if(voiceSession===session){cancelVoice(true);toast('录音中断，请检查麦克风后重试。');}};
    session.recorder.start(1000);session.started=Date.now();session.phase='recording';
    syncVoiceControls();updateVoiceTime(session);startVoiceWaveform(session);
    session.clock=setInterval(()=>updateVoiceTime(session),250);
    session.timer=setTimeout(()=>{if(voiceSession===session)stopVoice();},60000);
  }catch(e){
    if(!session.cancelled&&voiceSession===session){
      cancelVoice(true);
      toast(e.name==='NotAllowedError'?'麦克风未获授权。请在浏览器地址栏允许麦克风，或直接输入文字。':e.name==='NotFoundError'?'未找到麦克风，请连接设备后重试。':e.message||'无法开始录音');
    }
  }
}
function stopVoice(sendAfter=false){
  const session=voiceSession;
  if(!session||session.phase!=='recording'||session.recorder?.state!=='recording')return;
  session.sendAfter=sendAfter;session.phase='transcribing';
  syncVoiceControls();session.recorder.stop();releaseMicrophone(session);
  $('voice-cancel').focus();
}
async function finishVoice(session){
  releaseMicrophone(session);
  if(session.cancelled||voiceSession!==session)return;
  session.phase='transcribing';syncVoiceControls();let submit=false;
  try{
    const blob=new Blob(session.parts,{type:session.mime});
    if(blob.size>4000000)throw Error('录音超过4MB，请缩短后重试。');
    if(blob.size<100)throw Error('录音太短，请重试。');
    const extension=session.mime.includes('webm')?'webm':session.mime.includes('ogg')?'ogg':'mp4';
    const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('读取录音失败，请重试。'));reader.readAsDataURL(blob);});
    if(session.cancelled||voiceSession!==session)return;
    const data=await api('/api/audio/transcribe',{method:'POST',signal:session.controller.signal,body:JSON.stringify({filename:'recording.'+extension,content_base64:encoded})});
    if(session.cancelled||voiceSession!==session)return;
    const transcript=typeof data.text==='string'?data.text.trim():'';
    if(!transcript)throw Error('没有识别到语音，请靠近麦克风后重试。');
    const previous=$('question').value,text=previous+(previous?'\n':'')+transcript;
    if(text.length>$('question').maxLength)throw Error('识别文字与输入内容合计超过字数上限，请精简后重试。');
    $('question').value=text;$('question').dispatchEvent(new Event('input'));$('question').focus();
    submit=session.sendAfter;
    if(!submit)toast('已转成文字，可修改后发送');
  }catch(e){
    if(e.name!=='AbortError'&&!session.cancelled)toast(e.message||'语音识别失败，请重试或输入文字');
  }finally{
    if(voiceSession===session){voiceSession=null;syncVoiceControls();}
    session.parts=[];
  }
  if(submit&&!session.cancelled&&session.sequence===voiceSequence&&!sending)$('composer').requestSubmit();
}
$('voice-input').onclick=startVoice;
$('voice-stop').onclick=()=>stopVoice();
$('voice-cancel').onclick=()=>cancelVoice(true);
// Capture clicks before native form validation: the draft may be empty while recording.
$('send').addEventListener('click',event=>{if(voiceSession){event.preventDefault();stopVoice(true);}},true);
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&voiceSession){event.preventDefault();cancelVoice(true);}
});
window.addEventListener('beforeunload',()=>cancelVoice());
