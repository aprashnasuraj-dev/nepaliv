from __future__ import annotations
import json, os, random, shutil, time
from pathlib import Path
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Signal, Slot, Qt, QSettings
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QCheckBox,QComboBox,QDoubleSpinBox,QFileDialog,QFormLayout,QGridLayout,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QMainWindow,QMessageBox,QPlainTextEdit,QProgressBar,QPushButton,QSlider,QSpinBox,QTabWidget,QTableWidget,QTableWidgetItem,QTextEdit,QVBoxLayout,QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from app.runtime import local_app_data
from app.pipeline.nepali_text import romanize,syllabify_line
from app.pipeline.user_lexicon import tts_text_for_line,save_user_lexicon,user_lexicon_path,load_user_lexicon
from app.pipeline.lyrics import generate_lyrics
from app.pipeline.local_render import RenderCancelled,render_song_local,speak_lyrics
from app.pipeline.styles import STYLES
from app.pipeline.tts import VOICES
STAGE={"lyrics":"लेख्दै","composing":"धुन बनाउँदै","singing":"गाउँदै","harmony":"हार्मोनी","band":"बाजा बजाउँदै","mixing":"मिक्स गर्दै","done":"तयार"}
def appdir(name):p=local_app_data()/name;p.mkdir(parents=True,exist_ok=True);return p
def feedback_path():return appdir("")/"feedback.jsonl"
def lyrics_to_text(x):
 a=[]
 for s in x.get("sections",[]):a += ["[Chorus]" if s.get("type")=="chorus" else "[Verse]",*s.get("lines",[]),""]
 return "\n".join(a).strip()
def text_to_lyrics(text,title="मेरो गीत"):
 sections=[];cur=None
 for raw in text.splitlines():
  x=raw.strip();low=x.lower()
  if not x:continue
  if low in ("[verse]","[अन्तरा]","[antara]"):cur={"type":"verse","lines":[]};sections.append(cur);continue
  if low in ("[chorus]","[स्थायी]","[मुखडा]","[mukhda]"):cur={"type":"chorus","lines":[]};sections.append(cur);continue
  if cur is None:cur={"type":"verse","lines":[]};sections.append(cur)
  cur["lines"].append(x)
 sections=[s for s in sections if s["lines"]]
 if not sections:raise ValueError("Lyrics are empty")
 return {"title":title or "मेरो गीत","sections":sections}
class Sig(QObject):progress=Signal(str,int,str);result=Signal(object);error=Signal(str);finished=Signal()
class Task(QRunnable):
 def __init__(self,fn):super().__init__();self.fn=fn;self.signals=Sig()
 @Slot()
 def run(self):
  try:self.signals.result.emit(self.fn())
  except Exception as e:self.signals.error.emit(f"{type(e).__name__}: {e}")
  finally:self.signals.finished.emit()
class RenderTask(QRunnable):
 def __init__(self,req,out):super().__init__();self.req=req;self.out=out;self.cancelled=False;self.signals=Sig()
 @Slot()
 def run(self):
  try:self.signals.result.emit(render_song_local(self.req,self.out,lambda s,p,m:self.signals.progress.emit(s,p,m),lambda:self.cancelled,True))
  except RenderCancelled:self.signals.error.emit("Generation cancelled")
  except Exception as e:self.signals.error.emit(f"{type(e).__name__}: {e}")
  finally:self.signals.finished.emit()
class MainWindow(QMainWindow):
 def __init__(self):
  super().__init__();load_user_lexicon();self.resize(1220,820);self.setWindowTitle("नेपाली AI Song Generator — Windows Test Studio");self.pool=QThreadPool.globalInstance();self.q=QSettings("NepaliSongGen","NepaliSongGen");self.lyrics=None;self.result=None;self.job=None;self.ab={};self.ab_map={};self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.audio.setVolume(.85);self.player.setAudioOutput(self.audio);self.player.positionChanged.connect(self._pos);self.player.durationChanged.connect(lambda d:self.seek.setRange(0,d));self.tabs=QTabWidget();self.setCentralWidget(self.tabs);self._create_tab();self._diag_tab();self._settings_tab();self.prompt.setPlainText("आमाको माया")
 def _create_tab(self):
  w=QWidget();v=QVBoxLayout(w);g=QGridLayout();self.prompt=QTextEdit();self.prompt.setMaximumHeight(80);g.addWidget(QLabel("Prompt"),0,0);g.addWidget(self.prompt,0,1,1,7);self.occasion=QComboBox();self.occasion.addItems(["","जन्मदिन","दसैँ","तिहार","तीज","माया","आमा","परदेश","लोरी","भजन"]);self.who=QLineEdit();self.style=QComboBox();self.style.addItems(list(STYLES));self.style.setCurrentText("adhunik");self.voice=QComboBox()
  for k,x in VOICES.items():
   if x.engine=="piper":self.voice.addItem(f"{x.label} · {x.license}",k)
  self.length=QComboBox();self.length.addItem("Short (~1 min)","short");self.length.addItem("Full (~2 min)","full");self.seed=QSpinBox();self.seed.setRange(0,2147483647);self.seed.setValue(random.randint(1,999999));self.harmony=QCheckBox("Harmony");self.harmony.setChecked(True);self.key=QSpinBox();self.key.setRange(-6,6);self.tempo=QDoubleSpinBox();self.tempo.setRange(.75,1.3);self.tempo.setValue(1)
  for i,(n,c) in enumerate((("Occasion",self.occasion),("For whom",self.who),("Style",self.style),("Voice",self.voice),("Length",self.length),("Seed",self.seed),("Key shift",self.key),("Tempo",self.tempo))):g.addWidget(QLabel(n),1+i//4,(i%4)*2);g.addWidget(c,1+i//4,(i%4)*2+1)
  self.write=QPushButton("1 · Write lyrics");self.write.clicked.connect(self.write_lyrics);self.singbtn=QPushButton("2 · Sing");self.singbtn.clicked.connect(self.sing);self.cancel=QPushButton("Cancel");self.cancel.clicked.connect(self.cancel_job);self.cancel.setEnabled(False);g.addWidget(self.harmony,3,0);g.addWidget(self.write,3,4);g.addWidget(self.singbtn,3,5);g.addWidget(self.cancel,3,6);v.addLayout(g);h=QHBoxLayout();self.editor=QPlainTextEdit();self.editor.setFont(QFont("Nirmala UI",11));self.editor.textChanged.connect(self.refresh_lines);h.addWidget(self.editor,3);self.lines=QTableWidget(0,4);self.lines.setHorizontalHeaderLabels(["Line","Syl","Roman","Actual TTS text"]);self.lines.horizontalHeader().setStretchLastSection(True);h.addWidget(self.lines,4);v.addLayout(h,1);ph=QHBoxLayout();self.progress=QProgressBar();self.status=QLabel("Ready");ph.addWidget(self.progress,3);ph.addWidget(self.status,2);v.addLayout(ph);p=QGroupBox("Player + karaoke");pv=QVBoxLayout(p);r=QHBoxLayout();self.play=QPushButton("▶ Play");self.play.clicked.connect(self.toggle);self.seek=QSlider(Qt.Horizontal);self.seek.sliderMoved.connect(self.player.setPosition);self.clock=QLabel("00:00 / 00:00");r.addWidget(self.play);r.addWidget(self.seek,1);r.addWidget(self.clock);pv.addLayout(r);self.karaoke=QLabel("—");self.karaoke.setAlignment(Qt.AlignCenter);self.karaoke.setWordWrap(True);self.karaoke.setFont(QFont("Nirmala UI",18));pv.addWidget(self.karaoke);ex=QHBoxLayout();b=QPushButton("Open output folder");b.clicked.connect(self.open_folder);e=QPushButton("Export MP3 as…");e.clicked.connect(self.export_mp3);ex.addWidget(b);ex.addWidget(e);ex.addStretch();pv.addLayout(ex);v.addWidget(p);self.tabs.addTab(w,"Create")
 def _diag_tab(self):
  w=QWidget();v=QVBoxLayout(w);v.addWidget(QLabel("Intelligibility diagnostics: plain TTS vs song, stems, blind A/B, wrong-word feedback and pitch view."));r=QHBoxLayout()
  for text,fn in (("Speak lyrics",self.speak),("A cappella",lambda:self.play_path(getattr(self.result,"vocal",None))),("Band",lambda:self.play_path(getattr(self.result,"band",None))),("Open stems",self.open_folder)):b=QPushButton(text);b.clicked.connect(fn);r.addWidget(b)
  v.addLayout(r);ab=QGroupBox("Blind A/B");ar=QHBoxLayout(ab);prep=QPushButton("Prepare A/B");prep.clicked.connect(self.prepare_ab);ar.addWidget(prep)
  for label in "AB":b=QPushButton(f"Play {label}");b.clicked.connect(lambda _,x=label:self.play_path(self.ab.get(x)));ar.addWidget(b);q=QPushButton(f"{label} clearer");q.clicked.connect(lambda _,x=label:self.vote_ab(x));ar.addWidget(q)
  self.abstatus=QLabel("Not prepared");ar.addWidget(self.abstatus);v.addWidget(ab);fb=QGroupBox("Wrong word / lexicon correction");f=QGridLayout(fb);self.bad=QLineEdit();self.problem=QComboBox();self.problem.addItems(["wrong sound","wrong split","unclear","too fast"]);self.expected=QLineEdit();save=QPushButton("Save feedback");save.clicked.connect(self.save_feedback);self.lexword=QLineEdit();self.lexparts=QLineEdit();self.lexparts.setPlaceholderText("जन्|म|दिन");lex=QPushButton("Save lexicon & re-analyse");lex.clicked.connect(self.save_lexicon)
  for i,(n,x) in enumerate((("Word",self.bad),("Problem",self.problem),("Expected",self.expected),("Lexicon word",self.lexword),("Syllables |",self.lexparts))):f.addWidget(QLabel(n),i,0);f.addWidget(x,i,1)
  f.addWidget(save,2,2);f.addWidget(lex,4,2);v.addWidget(fb);self.diag=QTableWidget(0,5);self.diag.setHorizontalHeaderLabels(["Line","TTS text","Roman","Syllables","Timing / pitch"]);self.diag.horizontalHeader().setStretchLastSection(True);self.diag.cellClicked.connect(lambda r,c:self.plot_line(r));v.addWidget(self.diag,1);self.fig=Figure(figsize=(8,2.1),tight_layout=True);self.canvas=FigureCanvas(self.fig);v.addWidget(self.canvas);self.tabs.addTab(w,"Diagnostics")
 def _settings_tab(self):
  w=QWidget();f=QFormLayout(w);self.models=QLineEdit(str(self.q.value("models_dir",local_app_data()/"models")));self.out=QLineEdit(str(self.q.value("output_dir",appdir("exports"))));self.threads=QSpinBox();self.threads.setRange(1,32);self.threads.setValue(int(self.q.value("threads",max(1,min(4,os.cpu_count() or 2)))));self.bitrate=QComboBox();self.bitrate.addItems(["128k","160k","192k","256k"]);self.bitrate.setCurrentText(str(self.q.value("bitrate","160k")));self.gemini=QLineEdit();self.groq=QLineEdit();self.openrouter=QLineEdit()
  for x in (self.gemini,self.groq,self.openrouter):x.setEchoMode(QLineEdit.Password)
  self.oref=QLineEdit(str(self.q.value("omnivoice_ref_audio","")));self.otext=QLineEdit(str(self.q.value("omnivoice_ref_text","")))
  for n,x in (("Models folder",self.models),("Output folder",self.out),("CPU threads",self.threads),("MP3 bitrate",self.bitrate),("Gemini key",self.gemini),("Groq key",self.groq),("OpenRouter key",self.openrouter),("Omni consented ref",self.oref),("Omni ref transcript",self.otext)):f.addRow(n,x)
  r=QHBoxLayout();s=QPushButton("Save settings");s.clicked.connect(self.save_settings);d=QPushButton("Download / verify Piper models");d.clicked.connect(self.download_models);r.addWidget(s);r.addWidget(d);f.addRow(r);self.dlstatus=QLabel("Model weights are not bundled. OmniVoice remains Experimental until its missing tokenizer weights, CPU RTF and listener gate pass.");self.dlstatus.setWordWrap(True);f.addRow(self.dlstatus);self.tabs.addTab(w,"Settings");self.load_keys()
 def request(self,with_lyrics=True):
  q={"prompt":self.prompt.toPlainText().strip(),"occasion":self.occasion.currentText() or None,"dedicate_to":self.who.text().strip() or None,"style":self.style.currentText(),"voice":self.voice.currentData(),"length":self.length.currentData(),"seed":self.seed.value(),"harmony":self.harmony.isChecked(),"key_shift":self.key.value(),"tempo_scale":self.tempo.value()}
  if with_lyrics:q["lyrics"]=text_to_lyrics(self.editor.toPlainText(),(self.lyrics or {}).get("title","मेरो गीत"))
  return q
 def write_lyrics(self):
  self.write.setEnabled(False);q=self.request(False);self.status.setText("लेख्दै…");t=Task(lambda:generate_lyrics(q,q["seed"]));t.signals.result.connect(self.lyrics_ready);t.signals.error.connect(self.err);t.signals.finished.connect(lambda:self.write.setEnabled(True));self.pool.start(t)
 def lyrics_ready(self,x):self.lyrics=x;self.editor.setPlainText(lyrics_to_text(x));self.status.setText("Lyrics ready · editable")
 def refresh_lines(self):
  try:x=text_to_lyrics(self.editor.toPlainText(),(self.lyrics or {}).get("title","मेरो गीत"))
  except Exception:return
  self.lyrics=x;rows=[]
  for s in x["sections"]:
   for line in s["lines"]:syl=syllabify_line(line);rows.append((line,len(syl),romanize(line),tts_text_for_line(line)," · ".join(y.text for y in syl)))
  self.lines.setRowCount(len(rows));self.diag.setRowCount(len(rows))
  for i,row in enumerate(rows):
   for j,z in enumerate(row[:4]):self.lines.setItem(i,j,QTableWidgetItem(str(z)))
   for j,z in enumerate((row[0],row[3],row[2],row[4],"")):self.diag.setItem(i,j,QTableWidgetItem(str(z)))
 def sing(self):
  try:q=self.request(True)
  except Exception as e:return self.err(str(e))
  self.singbtn.setEnabled(False);self.cancel.setEnabled(True);self.job=RenderTask(q,Path(self.out.text()));self.job.signals.progress.connect(lambda s,p,m:(self.progress.setValue(p),self.status.setText(f"{STAGE.get(s,s)} · {p}%")));self.job.signals.result.connect(self.render_ready);self.job.signals.error.connect(self.err);self.job.signals.finished.connect(self.job_done);self.pool.start(self.job)
 def cancel_job(self):
  if self.job:self.job.cancelled=True;self.status.setText("Cancelling after current safe step…")
 def job_done(self):self.singbtn.setEnabled(True);self.cancel.setEnabled(False);self.job=None
 def render_ready(self,x):
  self.result=x;self.status.setText(f"Done in {x.seconds:.1f}s");self.progress.setValue(100);self.play_path(x.mp3)
  for i,l in enumerate(x.karaoke.get("lines",[])):
   if i<self.diag.rowCount():self.diag.setItem(i,4,QTableWidgetItem(f"{l['start']:.2f}–{l['end']:.2f}s"))
 def play_path(self,path):
  if path and Path(path).exists():self.player.setSource(QUrl.fromLocalFile(str(Path(path))));self.player.play();self.play.setText("⏸ Pause")
 def toggle(self):
  if self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause();self.play.setText("▶ Play")
  else:self.player.play();self.play.setText("⏸ Pause")
 def _pos(self,p):
  self.seek.setValue(p);d=self.player.duration();self.clock.setText(f"{p//60000:02d}:{(p//1000)%60:02d} / {d//60000:02d}:{(d//1000)%60:02d}")
  if not self.result:return
  t=p/1000
  for l in self.result.karaoke.get("lines",[]):
   if l["start"]<=t<=l["end"]+.25:self.karaoke.setText("".join(f"<span style='background:#ffd54f;color:#111'>{s['t']}</span>" if s["start"]<=t<=s["end"] else s["t"] for s in l.get("syllables",[])));break
 def speak(self):
  try:x=text_to_lyrics(self.editor.toPlainText(),(self.lyrics or {}).get("title","गीत"))
  except Exception as e:return self.err(str(e))
  out=appdir("data/eval")/"plain-speech.wav";t=Task(lambda:speak_lyrics(x,self.voice.currentData(),out));t.signals.result.connect(self.play_path);t.signals.error.connect(self.err);self.pool.start(t)
 def prepare_ab(self):
  try:x=text_to_lyrics(self.editor.toPlainText());line=next(l for s in x["sections"] for l in s["lines"])
  except Exception as e:return self.err(str(e))
  order=["ne_NP-chitwan-medium","ne_NP-google-medium"];random.shuffle(order);mini={"title":"AB","sections":[{"type":"verse","lines":[line]}]};out=appdir("data/eval")
  def fn():return speak_lyrics(mini,order[0],out/"ab-A.wav"),speak_lyrics(mini,order[1],out/"ab-B.wav"),order,line
  t=Task(fn);t.signals.result.connect(self.ab_ready);t.signals.error.connect(self.err);self.abstatus.setText("Preparing…");self.pool.start(t)
 def ab_ready(self,x):a,b,o,l=x;self.ab={"A":a,"B":b};self.ab_map={"A":o[0],"B":o[1],"line":l};self.abstatus.setText("Ready — listen before voting")
 def vote_ab(self,w):
  if w not in self.ab_map:return
  self.log({"type":"ab_voice","line":self.ab_map["line"],"winner":self.ab_map[w],"loser":self.ab_map["B" if w=="A" else "A"]});self.abstatus.setText(f"Recorded: {w} clearer")
 def log(self,d):
  d={"ts":time.time(),**d}
  with feedback_path().open("a",encoding="utf-8") as f:f.write(json.dumps(d,ensure_ascii=False)+"\n")
 def save_feedback(self):
  if not self.bad.text().strip():return self.err("Enter a word")
  self.log({"type":"word","word":self.bad.text().strip(),"problem":self.problem.currentText(),"expected":self.expected.text().strip(),"voice":self.voice.currentData(),"style":self.style.currentText()});self.status.setText("Feedback saved")
 def save_lexicon(self):
  word=self.lexword.text().strip();parts=[x.strip() for x in self.lexparts.text().replace(",","|").split("|") if x.strip()]
  if not word or not parts:return self.err("Enter word and | separated syllables")
  p=user_lexicon_path();data={}
  if p.exists():
   try:data=json.loads(p.read_text(encoding="utf-8"))
   except Exception:pass
  data[word]=parts;save_user_lexicon(data);self.refresh_lines();self.status.setText(f"Lexicon saved: {word}")
 def plot_line(self,row):
  if not self.result or row>=len(self.result.karaoke.get("lines",[])):return
  try:
   import numpy as np,soundfile as sf,pyworld as pw
   l=self.result.karaoke["lines"][row];y,sr=sf.read(self.result.vocal,dtype="float32",always_2d=True);y=y.mean(1);a=max(0,int((l["start"]-.15)*sr));b=min(len(y),int((l["end"]+.15)*sr));seg=y[a:b];ax=self.fig.clear().add_subplot(111);ax.specgram(seg,NFFT=1024,Fs=sr,noverlap=896);ax.set_ylim(0,6000);errs=[]
   for s in l.get("syllables",[]):
    ax.axvline(max(0,float(s["start"])-l["start"]+.15),lw=.7);x0=max(0,int((s["start"]-l["start"]+.15)*sr));x1=min(len(seg),int((s["end"]-l["start"]+.15)*sr))
    if x1-x0>int(.06*sr) and "midi" in s:
     c=np.asarray(seg[x0:x1],dtype=np.float64);f0,t=pw.dio(c,sr,frame_period=5,f0_floor=60,f0_ceil=600);f0=pw.stonemask(c,f0,t,sr);vv=f0[f0>0]
     if len(vv):target=440*2**((float(s["midi"])-69)/12);errs.append(float(np.median(np.abs(1200*np.log2(vv/target)))))
   med=float(np.median(errs)) if errs else float("nan");ax.set_title(l.get("text","")+(f" | pitch {med:.0f} cents" if errs else ""),fontname="Nirmala UI");self.canvas.draw_idle()
   if errs:self.diag.setItem(row,4,QTableWidgetItem(f"{l['start']:.2f}–{l['end']:.2f}s · pitch {med:.0f}c"))
  except Exception as e:self.status.setText(f"Plot unavailable: {e}")
 def load_keys(self):
  try:
   import keyring
   for e,n in ((self.gemini,"GEMINI_API_KEY"),(self.groq,"GROQ_API_KEY"),(self.openrouter,"OPENROUTER_API_KEY")):e.setText(keyring.get_password("NepaliSongGen",n) or "")
  except Exception:pass
 def save_settings(self):
  vals={"models_dir":self.models.text().strip(),"output_dir":self.out.text().strip(),"threads":self.threads.value(),"bitrate":self.bitrate.currentText(),"omnivoice_ref_audio":self.oref.text().strip(),"omnivoice_ref_text":self.otext.text().strip()}
  for k,v in vals.items():self.q.setValue(k,v)
  for k,e in (("models_dir","VOICES_DIR"),("threads","TTS_THREADS"),("bitrate","MP3_BITRATE"),("omnivoice_ref_audio","OMNIVOICE_REF_AUDIO"),("omnivoice_ref_text","OMNIVOICE_REF_TEXT")):os.environ[e]=str(vals[k])
  try:
   import keyring
   for edit,n in ((self.gemini,"GEMINI_API_KEY"),(self.groq,"GROQ_API_KEY"),(self.openrouter,"OPENROUTER_API_KEY")):keyring.set_password("NepaliSongGen",n,edit.text().strip());os.environ[n]=edit.text().strip()
  except Exception as e:return self.err(f"Credential Manager: {e}")
  from app.config import get_settings;get_settings.cache_clear();self.status.setText("Settings saved")
 def download_models(self):
  dest=Path(self.models.text());self.dlstatus.setText("Downloading / verifying…")
  def fn():
   from scripts.fetch_models import load_manifest,selected_files,download
   for x in selected_files(load_manifest(),"voices"):download(x,dest,True)
   return str(dest)
  t=Task(fn);t.signals.result.connect(lambda p:self.dlstatus.setText(f"Verified: {p}"));t.signals.error.connect(lambda e:self.dlstatus.setText("FAILED: "+e));self.pool.start(t)
 def open_folder(self):p=Path(self.out.text());p.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
 def export_mp3(self):
  if not self.result:return
  d,_=QFileDialog.getSaveFileName(self,"Export MP3",self.result.mp3.name,"MP3 (*.mp3)")
  if d:shutil.copy2(self.result.mp3,d)
 def err(self,msg):self.status.setText("ERROR: "+str(msg));QMessageBox.critical(self,"Nepali Song Generator",str(msg))
