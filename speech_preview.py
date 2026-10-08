#!/usr/bin/env python3
"""Normal window for preview-only typed and spoken grammar debugging."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import wave
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gio, GLib, Gtk, Gdk
from speech.grammar import Grammar
from speech import history, openai_fallback, learning
from speech.storage import STATE, DATABASE, RECORDINGS, migrate
from speech.storage import DATA
from settings import Settings
from installed_apps import discover_installed_apps
from window_vocabulary import inject_windows
from os_actions import capture_window_context

ROOT=Path(__file__).resolve().parent
APP_ID='io.github.gregorycoppola.Skipper.VoicePreview'
GATE=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/'skipper-voice-held'


class Preview(Gtk.Application):
    def __init__(self, debug=True):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.debug=debug
        self.add_main_option('debug',0,GLib.OptionFlags.NONE,GLib.OptionArg.NONE,
                             'Open the separate preview-only debugger',None)
        self.add_main_option("speech",0,GLib.OptionFlags.NONE,GLib.OptionArg.NONE,
                             "Open the debugger with local Parakeet speech enabled",None)
        self.model=None;self.recorder=None;self.audio_file=None;self.phase='idle';self.window=None
        self.active_observation=None;self.latest=None;self.latest_audio=None;self.latest_observation=None;self.session=uuid.uuid4().hex;self.generation=0
        for name,fn in [('record-start',self.start_recording),('record-stop',self.stop_recording),('quit',self.close)]:
            action=Gio.SimpleAction.new(name,None);action.connect('activate',lambda a,p,fn=fn:fn());self.add_action(action)

    def do_command_line(self, command_line):
        self.activate()
        if command_line.get_options_dict().contains('debug'):
            self.debug=True
            self.window.present()
        if not self.debug or command_line.get_options_dict().contains("speech"):
            self.window.set_title("Skipper speech debugger · Parakeet")
            self.enable_speech()
            self.speech_button.grab_focus()
        return 0

    def do_activate(self):
        if self.window:
            if self.debug:self.window.present()
            return
        if not self.debug:self.hold()
        STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
        migrate()
        RECORDINGS.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(DATABASE)
        self.db.execute('CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, created TEXT, data TEXT, review TEXT, intended TEXT)')
        history.initialize(self.db)
        history.recover(self.db)
        css=Gtk.CssProvider()
        css.load_from_data(b'window { background: #162128; color: #edf3f5; } label { color: #edf3f5; } textview, textview text { background: #10191e; color: #edf3f5; } entry { background: #22323b; color: #ffffff; padding: 10px; border-radius: 6px; } button { background: #2d444c; color: #ffffff; padding: 10px; border-radius: 6px; }')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.db.commit()
        self.window=Gtk.ApplicationWindow(application=self,title='Skipper parser debugger')
        self.window.set_default_size(780,690)
        self.window.set_titlebar(Gtk.HeaderBar())
        self.window.connect('close-request',self.close)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        for side in ('top','bottom','start','end'):getattr(box,'set_margin_'+side)(18)
        page=Gtk.ScrolledWindow(vexpand=True)
        page.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        page.set_child(box);self.window.set_child(page)
        heading=Gtk.Label(label='Try a sentence · type or speak',xalign=0);heading.add_css_class('title-1');box.append(heading)
        self.status=Gtk.Label(label='Type a sentence below. Speech is off; microphone is closed.',xalign=0,wrap=True);box.append(self.status)
        box.append(Gtk.Label(label='Preview only · typed and spoken commands never execute.',xalign=0,wrap=True))
        self.cloud=Gtk.CheckButton(label='Use OpenAI when text does not parse (text and grammar vocabulary only)')
        self.cloud.set_active(False);box.append(self.cloud)
        box.append(Gtk.Label(label='Free-form grammar test · Enter to parse',xalign=0))
        text_row=Gtk.Box(spacing=10);box.append(text_row)
        self.entry=Gtk.Entry(placeholder_text='e.g. open Chromium in workspace three and tile it',hexpand=True)
        self.entry.connect('activate',self.test_text);text_row.append(self.entry)
        parse_button=Gtk.Button(label='Parse text')
        parse_button.connect('clicked',lambda *_:self.test_text(self.entry));text_row.append(parse_button)
        box.append(Gtk.Label(label='Typed sentences use the speech grammar and only preview the result.',xalign=0,wrap=True))
        self.speech_button=Gtk.Button(label='Enable speech · hold Super + R when ready')
        self.speech_button.connect('clicked',self.enable_speech);box.append(self.speech_button)
        self.output=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll=Gtk.ScrolledWindow(vexpand=True,min_content_height=200);scroll.set_child(self.output);box.append(scroll)
        history_row=Gtk.Box(spacing=10);box.append(history_row)
        for label,direction in [('← Older',-1),('Newer →',1),('Latest',0)]:
            button=Gtk.Button(label=label)
            button.connect('clicked',lambda *_,direction=direction:self.browse_history(direction))
            history_row.append(button)
        self.history_label=Gtk.Label(xalign=0,wrap=True);box.append(self.history_label)
        self.mapping=Gtk.Entry(placeholder_text='Confirmed canonical command · edit if the suggestion is wrong')
        box.append(self.mapping)
        self.learn_buttons=[]
        learn_row=Gtk.Box(spacing=6);box.append(learn_row)
        for label,choice in [('Use once','once'),('Save wording','phrase_rule'),('Save mishearing','recognition_correction'),('Reject','reject')]:
            button=Gtk.Button(label=label)
            button.connect('clicked',lambda *_,choice=choice:self.accept_mapping(choice))
            learn_row.append(button);self.learn_buttons.append(button)
        self.disable_button=Gtk.Button(label='Disable saved rule for this result')
        self.disable_button.connect('clicked',self.disable_mapping);box.append(self.disable_button)
        self.intended=Gtk.Entry(placeholder_text='If wrong: what did you mean?');box.append(self.intended)
        row=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=10,row_spacing=10)
        row.set_max_children_per_line(3);box.append(row)
        for label,fn in [('Correct',lambda *_:self.review('correct')),('Wrong / missed',lambda *_:self.review('incorrect')),
                         ('Open Omarchy menu',lambda *_:subprocess.Popen(['omarchy-menu','toggle','root'])),
                         ('Open Skipper',lambda *_:subprocess.Popen(['gapplication','action','io.github.gregorycoppola.Skipper','type-command'])),
                         ('Quit controls',lambda *_:self.close())]:
            button=Gtk.Button(label=label);button.connect('clicked',fn);row.append(button)
        playback=Gtk.Button(label='Play last recording')
        playback.connect('clicked',lambda *_:self.play_recording())
        box.append(playback)
        if self.debug:self.window.present()
        self.entry.grab_focus()
        self.output.get_buffer().set_text('Try:\n• open Chromium\n• open Chromium in workspace three and tile it\n• switch to workspace two\n• maximize this window\n• tile all terminals\n• volume down\n• focus tab\n\nYou can speak any of the existing authored command phrases. Unknown wording is saved and can go to OpenAI for interpretation.')
        self.browse_history(0)

    def enable_speech(self,*_):
        if self.phase not in ('idle','error'):return
        self.phase='loading'
        self.speech_button.set_sensitive(False)
        self.status.set_text('Loading local Parakeet… You can still type. Microphone closed.')
        threading.Thread(target=self.load_model,daemon=True).start()

    def load_model(self):
        try:
            from speech.config import model_path
            path=model_path()
            if not path.is_dir():raise RuntimeError('Local Parakeet model is missing: '+str(path))
            self.model=subprocess.Popen([sys.executable,str(ROOT/'speech/worker.py'),str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            ready=json.loads(self.model.stdout.readline())
            if not ready.get('ready'):raise RuntimeError('Parakeet did not become ready')
            self.model_info=ready
            GLib.idle_add(self.ready)
        except Exception as exc:GLib.idle_add(self.fail,str(exc))

    def ready(self):
        if self.phase=='closed':return
        self.speech_button.set_label('Speech ready · hold Super + R to speak')
        self.phase='ready';self.status.set_text('Ready. Microphone closed. Hold Super + R to record.')
        if not self.debug:self.voice_status('Ready','Hold Super + R to speak.')
    def fail(self,message):
        if self.phase=='closed':return
        self.phase='ready' if hasattr(self,'model_info') and self.model and self.model.poll() is None else 'error'
        self.speech_button.set_sensitive(self.phase=='error')
        self.status.set_text('Error: '+message+' — microphone closed. Typing is available.')
        if not self.debug:self.voice_status('Error',message)

    def runtime_action(self,name,value):
        connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        actions=Gio.DBusActionGroup.get(connection,'io.github.gregorycoppola.Skipper',
                                      '/io/github/gregorycoppola/Skipper')
        actions.activate_action(name,GLib.Variant('s',value))

    def voice_status(self,state,message,transcript=''):
        if self.debug:return
        self.runtime_action('voice-status',json.dumps({'state':state,'message':message,
                            'transcript':transcript}))

    def start_recording(self):
        if self.phase!='ready':
            if not getattr(self,'debug',True):self.voice_status('Error','Speech is loading. Try again when ready.' if self.phase=='loading' else 'Speech is unavailable. Restart voice input.')
            return
        if not GATE.exists() or GATE.read_text().strip()!='1':return
        self.generation+=1;self.record_generation=self.generation
        self.record_mode='debug' if self.debug else 'execute'
        self.take=uuid.uuid4().hex;self.started=time.monotonic();self.context=capture_window_context() or {}
        try:held=GATE.read_text().strip()=='1'
        except OSError:held=False
        if not held:return
        # Capture starts only in this action; no idle stream or pre-roll exists.
        self.raw_path=RECORDINGS/(self.take+'.pcm')
        self.active_observation={'id':self.take,'mode':self.record_mode,'source':'microphone',
            'session':self.session,'context':self.context,'raw_audio':str(self.raw_path),
            'parsed':{'transcript':None,'status':'pending','candidates':[]},
            'outcome':{'status':'recording','execution':'not_executed'}}
        history.save(self.db,self.active_observation)
        try:
            self.audio_file=self.raw_path.open('wb')
            self.recorder=subprocess.Popen([sys.executable,str(ROOT/'speech/capture.py'),str(os.getpid())],stdout=self.audio_file,stderr=subprocess.DEVNULL)
        except Exception as exc:
            if self.audio_file:self.audio_file.close()
            self.audio_file=None;self.recording_failed(self.active_observation,str(exc),self.generation);return
        self.phase='recording';self.status.set_text('Listening — '+self.record_mode+' mode. Release either key to stop.')
        if self.debug:self.raise_preview()
        else:self.voice_status('Recording','Listening… Release either key to stop.')
        GLib.timeout_add_seconds(30,self.limit_recording,self.record_generation)
        GLib.timeout_add(10,self.check_gate,self.record_generation)

    def check_gate(self,generation):
        if self.phase!='recording' or self.record_generation!=generation:return False
        try:held=GATE.read_text().strip()=='1'
        except OSError:held=False
        if not held:self.stop_recording();return False
        return True

    def raise_preview(self):
        self.window.present()
        # Global shortcuts lack the activation token normally supplied by a click.
        # Ask the compositor to reveal this window, after target context is saved.
        try:
            target='class:^'+APP_ID.replace('.','[.]')+'$'
            subprocess.Popen(['hyprctl','dispatch',
                'hl.dsp.focus({ window = '+json.dumps(target)+' })'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def limit_recording(self,generation):
        if self.phase=='recording' and self.record_generation==generation:self.stop_recording()
        return False

    def stop_recording(self):
        if self.phase!='recording':return
        self.released=time.monotonic();self.phase='transcribing'
        # Terminate capture before waiting for files, parsing, or showing the window.
        self.recorder.terminate()
        if getattr(self,'active_observation',None):
            self.active_observation['outcome']['status']='transcribing'
            history.save(self.db,self.active_observation)
        self.status.set_text('Microphone closing. Transcribing the captured command…')
        if not getattr(self,'debug',True):self.voice_status('Transcribing','Recognizing speech…')
        threading.Thread(target=self.finish_recording,daemon=True).start()

    def finish_recording(self):
        generation=self.record_generation
        recorder=self.recorder
        audio_file=self.audio_file
        observation=json.loads(json.dumps(self.active_observation)) if self.active_observation else None
        try:
            if observation is None:return
            self.recorder.wait(timeout=1)
            if generation!=self.generation:return
            self.audio_file.close();self.audio_file=None
            samples=self.raw_path.read_bytes();self.raw_path.unlink()
            samples=samples[:len(samples)//2*2]
            if not samples:raise RuntimeError('No audio captured. Wait for Ready and hold the keys while speaking.')
            path=RECORDINGS/(self.take+'.wav')
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(samples)
            observation['audio']=str(path)
            observation['duration_seconds']=len(samples)/32000
            GLib.idle_add(self.checkpoint,json.loads(json.dumps(observation)),generation)
            self.model.stdin.write(json.dumps({'audio':str(path)})+'\n');self.model.stdin.flush()
            response=json.loads(self.model.stdout.readline())
            if not response.get('ok'):raise RuntimeError(response.get('error','Transcription failed'))
            transcript=response['text'];asr_done=time.monotonic()
            observation['parsed']['transcript']=transcript
            observation['model']=self.model_info
            observation['outcome']['status']='parsing'
            GLib.idle_add(self.checkpoint,json.loads(json.dumps(observation)),generation)
            grammar=self.make_grammar(self.context);parsed=grammar.parse(transcript)
            observation={'id':self.take,'session':self.session,'mode':self.record_mode,'source':'microphone','audio':str(path),'duration_seconds':len(samples)/32000,
                'context':self.context,'parsed':parsed,'model':self.model_info,'asr_seconds':response['inference_seconds'],
                'trailing_synthetic_silence_ms':response.get('trailing_synthetic_silence_ms',0),
                'empty_transcript_retry':response.get('empty_transcript_retry',False),
                'release_to_transcript_ms':(asr_done-self.released)*1000,'release_to_result_ms':(time.monotonic()-self.released)*1000,
                'timing_boundary':'application receives key-release action to preview decision; includes capture shutdown',
                'grammar_inventory':grammar.inventory()}
            GLib.idle_add(self.show_result,observation,generation,grammar)
        except Exception as exc:GLib.idle_add(self.recording_failed,observation,str(exc),generation)
        finally:
            if recorder.poll() is None:recorder.kill()
            audio_file.close()

    @staticmethod
    def make_grammar(context):
        return learning.LearnedGrammar(Grammar(context,discover_installed_apps(for_picker=True),inject_windows(context)))

    def test_text(self,entry):
        if self.phase in ('recording','transcribing','closed'):return
        observation={'id':uuid.uuid4().hex,'mode':'debug','source':'typed',
            'session':getattr(self,'session',None),
            'parsed':{'transcript':entry.get_text(),'status':'pending','candidates':[]},
            'outcome':{'status':'parsing','execution':'not_executed'}}
        history.save(self.db,observation)
        grammar=None
        try:
            context=capture_window_context() or {}
            observation['context']=context
            grammar=self.make_grammar(context)
            observation['grammar_inventory']=grammar.inventory()
            observation['parsed']=grammar.parse(entry.get_text())
            observation.pop('outcome')
        except Exception as exc:
            observation['parsed']['status']='error'
            observation['outcome']={'status':'error','execution':'not_executed','error':str(exc)}
        self.show_result(observation,self.generation,grammar)

    def checkpoint(self,observation,generation):
        if self.phase=='closed' or generation!=self.generation:return
        self.active_observation=observation
        history.save(self.db,observation)
        if not self.debug and observation['parsed'].get('transcript'):
            self.voice_status('Understanding','Interpreting…',observation['parsed']['transcript'])

    def recording_failed(self,observation,message,generation):
        observation['parsed']['status']='error'
        observation['outcome']={'status':'error','execution':'not_executed','error':message}
        self.show_result(observation,generation)
        self.fail(message)

    def browse_history(self,direction):
        if self.phase in ('recording','transcribing','closed'):return
        entries=list(history.rows(self.db))
        if not entries:
            self.history_label.set_text('No history yet. Type a sentence to begin.')
            return
        index=next((i for i,item in enumerate(entries) if item['id']==self.latest),len(entries)-1)
        index=len(entries)-1 if direction==0 else max(0,min(len(entries)-1,index+direction))
        observation=entries[index]
        self.latest=observation['id']
        self.intended.set_text(observation.get('intended') or '')
        self.render_result(observation)
        self.history_label.set_text(f"History {index+1}/{len(entries)} · {observation['created']} UTC · "
                                    + (observation.get('review') or 'unreviewed'))

    def show_result(self,observation,generation,grammar=None):
        if self.phase=='closed' or generation!=self.generation:return
        execute=(not getattr(self,'debug',True) and observation.get('mode')=='execute'
                 and observation['source']=='microphone')
        observation['mode']='execute' if execute else 'debug'
        observation.pop('execution',None)
        self.latest=observation['id'];self.intended.set_text('')
        observation=history.save(self.db,observation)
        if hasattr(self,'history_label'):self.history_label.set_text('Latest result · unreviewed')
        if observation['source']=='microphone':
            self.phase='ready';self.active_observation=None
        self.render_result(observation)
        if execute:
            parsed=observation['parsed']
            if parsed['status'] in ('matched','needs_selection','ambiguous'):
                self.runtime_action('execute-voice',observation['id'])
            elif (grammar is not None and parsed['status']=='unrecognized'
                  and parsed.get('transcript','').strip() and Settings(DATA/'settings.json').voice_cloud):
                observation['generation']=generation
                observation['llm']={'provider':'openai','status':'pending'}
                observation['outcome']={'status':'checking_openai','execution':'not_executed'}
                history.save(self.db,observation)
                self.voice_status('Understanding','Asking OpenAI…',parsed['transcript'])
                threading.Thread(target=self.run_fallback,args=(observation,grammar),daemon=True).start()
            else:
                self.voice_status('Error',observation.get('outcome',{}).get('error') or
                    ('No speech heard. Hold Super + R while speaking.' if not parsed.get('transcript')
                     else 'Could not understand that command. Try again.'),parsed.get('transcript') or '')
            return
        if (grammar is not None and observation['parsed']['status']=='unrecognized'
                and observation['parsed'].get('transcript','').strip() and self.cloud.get_active()):
            observation['llm']={'provider':'openai','status':'pending'}
            observation['outcome']={'status':'checking_openai','execution':'not_executed'}
            history.save(self.db,observation)
            self.render_result(observation)
            threading.Thread(target=self.run_fallback,args=(observation,grammar),daemon=True).start()

    def run_fallback(self,observation,grammar):
        result=openai_fallback.interpret(observation['parsed']['transcript'],grammar,observation_id=observation['id'])
        if result.get('parsed') and observation.get('mode')!='execute':
            result['proposal']=openai_fallback.propose(observation['parsed']['transcript'],result,grammar,observation['id'])
        GLib.idle_add(self.finish_fallback,observation,result)

    def finish_fallback(self,observation,result):
        if self.phase=='closed':return
        observation['llm']=result
        observation['outcome']={'status':'openai_'+result['status'],'execution':'not_executed'}
        observation=history.save(self.db,observation)
        if observation.get('mode')=='execute':
            if self.latest!=observation['id'] or observation.get('generation')!=self.generation:return
            if result.get('status')=='interpreted' and result.get('parsed'):
                self.runtime_action('execute-voice',observation['id'])
            else:
                self.voice_status('Error',result.get('reply',{}).get('clarification') or
                    result.get('error') or 'Could not interpret that command. Please rephrase.',
                    observation['parsed']['transcript'])
            return
        if self.latest==observation['id']:
            self.render_result(observation)
            self.history_label.set_text('OpenAI result saved · review the intended meaning')

    def render_result(self,observation):
        self.latest_observation=observation
        parsed=observation['parsed'];text=parsed.get('transcript') or '';status=parsed['status']
        self.latest_audio=observation.get('audio')
        llm=observation.get('llm') or {}
        confirmed=observation.get('confirmed') or {}
        self.mapping.set_text(confirmed.get('canonical_text') or llm.get('reply',{}).get('canonical_text') or '')
        can_learn=(status=='unrecognized' and bool(text.strip()) and llm.get('status')!='pending')
        self.mapping.set_sensitive(can_learn)
        for button in self.learn_buttons:button.set_sensitive(can_learn)
        self.disable_button.set_sensitive(bool(parsed.get('learned_rule_id') or confirmed.get('rule_id')))
        prefix='Heard' if observation['source']=='microphone' else 'Typed'
        lines=['1. ASR TRANSCRIPT' if observation['source']=='microphone' else '1. TYPED INPUT',
               text or '[Parakeet returned no transcript]', '', '2. SENTENCE PARSE']
        if not text.strip():lines.append('No transcript to parse. Play the recording, then repeat or type the command.')
        if observation.get('empty_transcript_retry'):lines.append('Parakeet retried locally with a longer silence tail after an empty first result.')
        elif not parsed['candidates']:lines.append('Transcript received, but no complete grammar rule matched.')
        for candidate in parsed['candidates']:
            lines.append('Rule: '+candidate.get('rule','unknown'))
            if candidate.get('pattern'):lines.append('Pattern: '+candidate['pattern'])
            for key,value in candidate.get('bindings',{}).items():lines.append('  <'+key+'> = '+str(value))
        if parsed.get('learned_rule_id'):
            lines.extend(['Learned '+parsed.get('learned_rule_kind','rule')+': '+parsed['learned_rule_id'],'Canonical: '+parsed['canonical_text']])
        lines.extend(['', '3. INTENT AND ARGUMENTS', 'Status: '+status.replace('_',' ')])
        for candidate in parsed['candidates']:
            if candidate.get('interaction'):
                lines.append('Selection required: '+candidate['interaction'])
            else:lines.append(json.dumps(candidate.get('canonical_plan',[]),indent=2))
            for key,value in candidate.get('launch_options',{}).items():
                if key=='workspace' and value=='current':value='current workspace ('+str(candidate.get('resolved_workspace'))+')'
                lines.append(key+': '+str(value)+' ['+candidate.get('argument_sources',{}).get(key,'explicit')+']')
        if observation.get('release_to_result_ms') is not None:
            lines.append('\nRelease to result: '+str(round(observation['release_to_result_ms']))+' ms')
        llm=observation.get('llm')
        if llm:
            lines.extend(['','4. OPENAI FALLBACK', 'Status: '+llm['status']])
            reply=llm.get('reply',{})
            if reply.get('canonical_text'):lines.append(('Possible mishearing — did you mean: ' if llm['status']=='mishearing' else 'Interpreted as: ')+reply['canonical_text'])
            proposal=llm.get('proposal',{})
            if proposal.get('status')=='proposed':
                patch=proposal['reply'];lines.extend(['Proposed '+patch['kind']+': '+patch['input_phrase']+' → '+patch['canonical_phrase'],patch['rationale']])
            elif proposal:lines.append('Proposal: '+proposal.get('error',proposal.get('status','unavailable')))
            if reply.get('clarification'):lines.append(reply['clarification'])
            if llm.get('error'):lines.append(llm['error'])
            for candidate in (llm.get('parsed') or {}).get('candidates',[]):
                lines.append(json.dumps({key:candidate[key] for key in
                    ('intent','canonical_plan','launch_options','argument_sources','interaction') if key in candidate},indent=2))
        if confirmed:lines.extend(['','USER CONFIRMED: '+confirmed['canonical_text'],'Remember as: '+confirmed['choice']])
        outcome=observation.get('outcome',{})
        if outcome:
            lines.extend(['','Outcome: '+outcome['status']])
            if outcome.get('error'):lines.append(outcome['error'])
        execution=observation.get('execution')
        lines.extend(['', ('EXECUTION: '+execution['message']) if execution else
                      'DEBUG — no desktop command was executed.', 'Mark Correct or Wrong / missed below.'])
        self.output.get_buffer().set_text('\n'.join(lines))
        self.status.set_text(prefix+': '+(text or 'no transcript')+' — microphone closed.')

    def accept_mapping(self,choice):
        if self.phase in ('recording','transcribing','closed'):return
        observation=getattr(self,'latest_observation',None)
        if not observation or observation['parsed']['status']!='unrecognized':return
        if (observation.get('llm') or {}).get('status')=='pending':return
        observation=json.loads(json.dumps(observation))
        try:
            if choice=='reject':
                with self.db:history.event(self.db,'suggestion_rejected',{'reply':(observation.get('llm') or {}).get('reply')},observation['id'])
                observation['outcome']={'status':'suggestion_rejected','execution':'not_executed'}
            else:
                canonical=self.mapping.get_text().strip()
                grammar=self.make_grammar(observation.get('context',{}))
                parsed=grammar.base.parse(canonical)
                if parsed['status'] not in ('matched','needs_selection') or len(parsed['candidates'])!=1:
                    raise ValueError('The corrected command must have one supported local intent.')
                original=observation['parsed']['transcript']
                confirmation={'canonical_text':canonical,'choice':choice,'parsed':parsed}
                if choice not in ('once','phrase_rule','recognition_correction'):raise ValueError('Unknown learning choice')
                with self.db:history.event(self.db,'meaning_confirmed',confirmation,observation['id'])
                if choice!='once':
                    proposal={'kind':choice,'input_phrase':original,'canonical_phrase':canonical,
                              'rationale':'User confirmed this exact mapping and selected its category.'}
                    rule=learning.approve(proposal,original,parsed,grammar,observation['id'])
                    confirmation['rule_id']=rule['id']
                    repeated=self.make_grammar(observation.get('context',{})).parse(original)
                    if repeated.get('learned_rule_id')!=rule['id'] or learning.meaning(repeated)!=learning.meaning(parsed):
                        learning.disable(rule['id'])
                        raise ValueError('Repeat check failed; the new rule was disabled.')
                    with self.db:history.event(self.db,'rule_repeat_verified',{'rule_id':rule['id'],'parsed':repeated},observation['id'])
                observation['confirmed']=confirmation
                observation['outcome']={'status':'confirmed_once' if choice=='once' else 'learned','execution':'not_executed'}
            observation=history.save(self.db,observation)
            self.render_result(observation)
            self.status.set_text('Rejected.' if choice=='reject' else 'Confirmed for this preview.' if choice=='once' else 'Saved. Repeat the phrase by typing or speaking to test local recognition.')
        except Exception as exc:
            with self.db:history.event(self.db,'learning_error',{'error':str(exc)},observation['id'])
            self.status.set_text('Could not save: '+str(exc))

    def disable_mapping(self,*_):
        if self.phase in ('recording','transcribing','closed'):return
        observation=getattr(self,'latest_observation',None)
        if not observation:return
        ident=observation['parsed'].get('learned_rule_id') or observation.get('confirmed',{}).get('rule_id')
        if not ident:return
        try:
            learning.disable(ident)
            self.disable_button.set_sensitive(False)
            self.status.set_text('Rule disabled. The next attempt will use the remaining grammar.')
        except Exception as exc:self.status.set_text('Could not disable: '+str(exc))

    def play_recording(self):
        if self.phase in ('recording','transcribing','closed'):return
        audio=self.latest_audio
        if not audio:
            row=self.db.execute("SELECT json_extract(data,'$.audio') FROM observations WHERE json_extract(data,'$.audio') IS NOT NULL ORDER BY rowid DESC LIMIT 1").fetchone()
            audio=row[0] if row else None
        if audio and Path(audio).is_file():subprocess.Popen(['pw-play',audio])

    def review(self,review):
        if not self.latest or self.phase in ('recording','transcribing','closed'):return
        with self.db:
            self.db.execute('UPDATE observations SET review=?,intended=? WHERE id=?',(review,self.intended.get_text(),self.latest))
            history.event(self.db,'review_saved',{'review':review,'intended':self.intended.get_text()},self.latest)
        if hasattr(self,'history_label'):self.history_label.set_text('Review saved · '+review)
        self.status.set_text('Review saved. Type another sentence, or speak when speech is ready.')

    def close(self,*_):
        if self.active_observation:
            self.active_observation['outcome']={'status':'interrupted','execution':'not_executed',
                'error':'Debugger closed during capture or transcription.'}
            history.save(self.db,self.active_observation)
            self.active_observation=None
        if hasattr(self,'db'):history.recover(self.db)
        self.phase='closed';self.generation+=1
        if self.recorder and self.recorder.poll() is None:self.recorder.kill()
        if self.model and self.model.poll() is None:self.model.terminate()
        self.quit();return False


if __name__=='__main__':
    os.umask(0o077)
    app=Preview(debug='--debug' in sys.argv)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,lambda: (app.close(),False)[1])
    app.run(sys.argv)
