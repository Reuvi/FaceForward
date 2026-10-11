"""Profile/source recovery and the compact App; no physical camera or OS events."""

import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from App.mouse_runtime import MouseSession
from App.paths import DEFAULT_MODEL, PROFILE_DIRECTORY

PIXELS = all(importlib.util.find_spec(name) for name in ('cv2','numpy'))


@unittest.skipUnless(PIXELS,'Vision dependencies required')
class SourcePreparationTests(unittest.TestCase):
    def setUp(self):
        self.session = MouseSession()
        self.addCleanup(self.session.close)

    def test_camera_profile_loads_before_camera_opens_and_survives_same_source_start(self):
        from Vision.calibration import EyeCalibration
        self.session.prepare_source('camera')
        core = self.session.ensure_detector_runtime().workbench
        core.eyes['left'] = EyeCalibration(.04,.25,.5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'profile.json'
            model = Path(directory)/'model.task'
            model.touch()
            self.session.save_profile(path)
            self.session.prepare_source('demo')
            self.session.prepare_source('camera')
            self.session.load_profile(path)
            self.assertIsNone(self.session.thread)
            self.assertIn('left',core.eyes)
            self.assertTrue(self.session.state()['profile_bound'])
            self.assertFalse(self.session.lab.processor.armed)
            with patch.object(self.session,'_camera') as camera:
                self.session.start('camera',model=model,count=1)
                self.session.thread.join(2)
                camera.assert_called_once()
            self.assertIn('left',core.eyes)
            self.assertTrue(self.session.state()['profile_bound'])

    def test_missing_model_does_not_erase_calibration_or_spawn_worker(self):
        from Vision.calibration import EyeCalibration
        self.session.prepare_source('camera')
        core = self.session.ensure_detector_runtime().workbench
        core.eyes['left'] = EyeCalibration(.04,.25,.5)
        with self.assertRaisesRegex(ValueError,'Camera model not found'):
            self.session.start('camera',model='/missing/face-model.task')
        self.assertIsNone(self.session.thread)
        self.assertIn('left',core.eyes)

    def test_cannot_select_another_source_while_worker_still_owns_camera(self):
        self.session.start('demo')
        with self.assertRaisesRegex(ValueError,'Wait for the current source'):
            self.session.prepare_source('camera')
        self.assertEqual(self.session.mode,'demo')

    def test_camera_failure_is_actionable_and_releases_output(self):
        from Vision.capture import CaptureError
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory)/'model.task'
            model.touch()
            with patch.object(self.session,'_camera',side_effect=CaptureError('cannot open camera 0')):
                self.session.start('camera',model=model)
                self.session.thread.join(2)
            state = self.session.state()
            self.assertIn('camera permissions',state['error'])
            self.assertIn('Camera ID',state['error'])
            self.assertFalse(state['running'])
            self.assertFalse(self.session.lab.state()['message']['enabled'])

    def test_default_asset_paths_do_not_depend_on_launch_directory(self):
        self.assertTrue(DEFAULT_MODEL.is_absolute())
        self.assertEqual(DEFAULT_MODEL.parent.parent.parent,PROFILE_DIRECTORY.parent)
        self.assertEqual(PROFILE_DIRECTORY.parent,Path(__file__).resolve().parents[2])


@unittest.skipUnless(PIXELS and os.environ.get('RUN_TK_TESTS')=='1','native Tk check')
class SimpleSignalsWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from App.desktop import IntegratedDesktop
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.model = Path(self.directory.name)/'model.task'
        self.model.touch()
        self.session = MouseSession()
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *error:self.errors.append(error)
        options = SimpleNamespace(source='demo',replay=None,model=str(self.model),fps=30,camera_id=0,no_preview=True,subject=None)
        with patch.object(IntegratedDesktop,'start_source'):
            self.ui = IntegratedDesktop(self.root,self.session,options)
        self.root.update()
        self.addCleanup(self.close)

    def close(self):
        self.ui.closed = True
        self.session.close()
        if self.ui.calibration_ui:
            self.ui.calibration_ui.close_panels()
        for timer in self.root.tk.splitlist(self.root.tk.call('after','info')):
            self.root.after_cancel(timer)
        self.root.destroy()
        self.assertEqual(self.errors,[])

    def until(self,predicate):
        deadline = time.monotonic()+3
        while not predicate() and time.monotonic()<deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(predicate())

    def profile(self):
        from Vision.calibration import EyeCalibration
        session = MouseSession()
        try:
            session.prepare_source('camera')
            session.ensure_detector_runtime().workbench.eyes['left'] = EyeCalibration(.04,.25,.5)
            path = Path(self.directory.name)/'camera.json'
            session.save_profile(path)
            return path
        finally:
            session.close()

    def load(self,path):
        with patch('App.desktop.filedialog.askopenfilename',return_value=str(path)):
            self.ui.load_profile()

    def test_stop_reason_and_pointer_blocker_stay_visible(self):
        self.session.lab.disconnect('Input stale; start preview again')
        self.ui.refresh()
        self.ui.refresh_vision()
        self.root.update()
        self.assertEqual(self.ui.status.get(),'Input stale; start preview again')
        self.assertIn('fresh',self.ui.pointer_detail.get())
        self.session.lab.output_error = 'Synthetic driver permission failure'
        self.ui.refresh_vision()
        self.assertIn('Synthetic driver permission failure',self.ui.pointer_detail.get())

    def test_mouse_test_selector_settings_and_instructions(self):
        self.session.lab.select_mapping('mouse-test')
        self.ui.refresh();self.root.update()
        panel=self.ui.mapping_page
        self.assertEqual(panel.selector.get(),'Mouse test')
        self.assertEqual(len(panel.table.get_children()),6)
        self.assertIn('calibrated wink or plain open/closed',panel.help_text.get())
        self.assertTrue(panel.wink_clicks.get())
        self.assertIn('Downward boost',panel.help_text.get())
        panel.show_settings();self.root.update()
        self.assertTrue(all(not group.winfo_ismapped() for group in panel.head_groups))
        self.assertFalse(panel.binding_group.winfo_ismapped())
        self.assertEqual(panel.down_gain.get(),'3')
        self.assertEqual(panel.pointer_fields['smoothing_ms'].get(),'20')
        self.assertTrue(panel.motion_group.winfo_ismapped())
        self.assertTrue(panel.motion_enabled.get())
        panel.wink_clicks.set(False)
        panel.motion_enabled.set(False)
        panel.motion_fields['speed_gain'].set('0.5')
        panel.motion_fields['return_brake'].set('0.4')
        panel.adaptive.set(False);panel._apply()
        self.ui.refresh();self.root.update()
        self.assertFalse(self.session.lab.state()['mapping']['head_wink_clicks'])
        self.assertEqual(len(panel.table.get_children()),4)
        self.assertIn('Eye actions are disabled',panel.help_text.get())
        self.assertFalse(self.session.lab.state()['mapping']['adaptive_pointer'])
        self.assertEqual(self.session.lab.state()['mapping']['input_mode'],'head-mouse')
        self.assertFalse(self.session.lab.processor.armed)
        self.assertEqual(self.session.lab.state()['mapping']['head_motion'],
                         dict(enabled=False,speed_gain=.5,return_brake=.4))
        from Processing.mouse.engine import AxisFilter
        self.assertIs(type(self.session.lab.processor.pointer),AxisFilter)
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        self.ui.refresh();self.root.update()
        self.assertTrue(all(group.winfo_ismapped() for group in panel.head_groups))
        self.assertTrue(panel.binding_group.winfo_ismapped())
        self.assertFalse(panel.motion_group.winfo_ismapped())

    def test_live_curve_editor_sliders_profiles_and_mapping_switch(self):
        self.session.lab.select_mapping('mouse-test')
        self.ui.refresh();self.ui.mapping_page.show_curves();self.root.update()
        editor=self.ui.mapping_page.curve_editor
        self.assertEqual(set(dict(editor.channel_choices)),{'pointer','left','right','mouth'})
        self.assertIn('speed_gain',editor.widgets)
        self.assertTrue(editor.curve_canvas.find_all())
        self.assertTrue(editor.time_canvas.find_all())
        editor.widgets['gain'][2].set(2.2)
        self.assertTrue(editor.flush())
        self.assertAlmostEqual(self.session.lab.state()['mapping']['pointer_gain'],2.2)
        self.assertIn('updated',editor.notice.get())
        self.assertFalse(self.session.lab.processor.armed)

        editor.selector.current(1);editor.select_channel();self.root.update()
        self.assertEqual(editor.channel,'left')
        self.assertEqual(editor.widgets,{})
        self.assertIn('ON/OFF',editor.explanation.get())
        path=Path(self.directory.name)/'response.json'
        editor.name.set('My precise head')
        with patch('Processing.tuning.view.filedialog.asksaveasfilename',return_value=str(path)):
            editor.save()
        self.assertTrue(path.is_file())
        editor.defaults()
        self.assertEqual(self.session.lab.state()['mapping']['pointer_gain'],1.4)
        with patch('Processing.tuning.view.filedialog.askopenfilename',return_value=str(path)):
            editor.load()
        self.assertEqual(editor.name.get(),'My precise head')
        self.assertAlmostEqual(self.session.lab.state()['mapping']['pointer_gain'],2.2)
        self.assertFalse(self.session.lab.processor.armed)
        editor.defaults()
        with patch('Processing.target_game.storage.DEFAULT_PATH',path):
            editor.personal_default()
        self.assertAlmostEqual(self.session.lab.state()['mapping']['pointer_gain'],2.2)
        self.assertFalse(self.session.lab.processor.armed)
        editor.selector.current(0);editor.select_channel()
        editor.widgets['gain'][2].set(3)
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        editor.refresh(self.session.lab.state())
        self.assertIsNone(editor.pending)
        self.assertEqual(self.session.lab.state()['mapping']['pointer_gain'],2)
        self.assertIn('head_x',dict(editor.channel_choices))
        self.assertIn('jitter',editor.widgets)
        self.assertNotIn('acceleration',editor.widgets)
        self.root.update()
        # Graphs, stop button and profile controls remain within the editor.
        self.assertLess(editor.time_canvas.winfo_rooty()+editor.time_canvas.winfo_height(),
                        editor.window.winfo_rooty()+editor.window.winfo_height())
        editor.hide();self.root.update()
        self.assertFalse(editor.window.winfo_viewable())
        editor.show();self.root.update()
        editor.stop()
        self.assertFalse(self.session.lab.processor.armed)

    def test_mouth_binary_channel_and_new_button_routes_are_connected(self):
        self.session.lab.select_mapping('mouse-test')
        self.ui.refresh();self.root.update()
        panel=self.ui.mapping_page
        self.assertEqual(panel.pointer_mode.get(),'Relative movement')
        self.assertEqual({k:v.get() for k,v in panel.button_bindings.items()},
                         dict(left_eye='w',right_eye='left_click',mouth='space'))
        self.assertIn('SPACE',panel.table.item('mouth','values')[-1])
        self.assertIn('W:',panel.table.item('eye_left','values')[-1])
        panel.show_curves();self.root.update()
        editor=panel.curve_editor
        editor.selector.current(next(i for i,(key,_) in enumerate(editor.channel_choices) if key=='mouth'))
        editor.select_channel();self.root.update()
        self.assertEqual(editor.widgets,{})
        self.assertIn('no calibration',editor.explanation.get())
        self.assertTrue(editor.curve_canvas.find_all())
        self.assertTrue(editor.time_canvas.find_all())
        panel.button_bindings['mouth'].set('w');panel._apply()
        self.ui.refresh();self.root.update()
        self.assertEqual(self.session.lab.state()['mapping']['button_bindings']['mouth'],'w')
        self.assertFalse(self.session.lab.processor.armed)

    def test_target_game_entry_reuses_window_and_keeps_two_main_tabs(self):
        from Processing.target_game.view import TargetGame
        with patch('Processing.target_game.view.TargetGame',wraps=TargetGame) as create:
            self.ui.show_target_game();self.root.update()
            game=self.ui.target_game
            self.ui.show_target_game();self.root.update()
            self.assertEqual(create.call_count,1)
            self.assertEqual(len(self.ui.notebook.tabs()),2)
            self.assertEqual(game.source()['mode'],self.session.mode)
            self.assertFalse(self.session.lab.processor.armed)
            game.close()
            self.assertTrue(game.closed)

    def test_eye_source_checkbox_and_head_recovery_buttons_are_connected(self):
        from Vision.mouse_demo import mouse_demo_records
        from Processing.mappings.demo import gaming_demo_frame
        self.session.lab.select_mapping('mouse-test')
        self.ui.refresh();self.root.update()
        panel=self.ui.mapping_page
        self.assertTrue(panel.center_button.winfo_ismapped())
        panel.show_curves();self.root.update()
        editor=panel.curve_editor
        self.assertTrue(editor.require_wink.get())
        self.session.lab.action({'action':'arm'})
        editor.eye_mode_button.invoke();self.root.update()
        self.assertFalse(self.session.lab.state()['mapping']['require_wink'])
        self.assertFalse(self.session.lab.processor.armed)
        self.assertIn('ordinary blinks',editor.notice.get())
        editor.selector.current(1);editor.select_channel();self.root.update()
        self.assertIn('Plain open/closed',editor.explanation.get())
        self.assertEqual(editor.widgets,{})
        editor.center_button.invoke();self.root.update()
        self.assertTrue(self.session.lab.processor.center_requested)
        self.assertIn('WAITING TO START',editor.connection.get())
        base=next(mouse_demo_records(count=1));base['timestamp_ms']=self.session.clock()
        frame=gaming_demo_frame(base,30)
        for key,value in (('head_x',.3),('head_y',.7)):
            frame['faces'][0]['signals'][key].update(value=value,valid=True,confidence=1)
        self.session.deliver(frame)
        self.ui.refresh();self.root.update()
        self.assertTrue(self.session.lab.processor.enabled)
        self.assertIn('0.300',panel.center_text.get())
        self.assertIn('RUNNING',editor.connection.get())
        panel.center_button.invoke()
        self.assertTrue(self.session.lab.processor.center_requested)
        self.session.lab.action({'action':'stop'})
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        self.ui.refresh();self.root.update()
        self.assertFalse(panel.center_button.winfo_ismapped())
        self.assertFalse(editor.center_button.winfo_ismapped())
        self.assertTrue(editor.require_wink.get())

    def test_presentation_controls_and_connected_brake_editor(self):
        from unittest.mock import Mock
        self.session.lab.select_mapping('presentation')
        self.ui.refresh();self.root.update()
        panel=self.ui.mapping_page
        self.assertEqual(panel.selector.get(),'Presentation')
        self.assertEqual(set(panel.table.get_children()),{'eye_left','eye_right','both_eyes','mouth_brake','head_pointer_x','head_pointer_y'})
        panel.show_settings();self.root.update()
        self.assertFalse(any(widget.winfo_ismapped() for widget in panel.button_widgets))
        self.assertEqual(str(panel.eye_enable['state']),'disabled')
        panel._apply();self.ui.refresh();self.root.update()
        panel.show_curves();self.root.update();editor=panel.curve_editor
        self.assertFalse(editor.require_wink.get())
        index=next(i for i,(key,_) in enumerate(editor.channel_choices) if key=='mouth_brake')
        editor.selector.current(index);editor.select_channel();self.root.update()
        self.assertEqual(set(editor.widgets),{'mouth_start','mouth_full','mouth_exponent'})
        self.assertIn('resistance',editor.explanation.get())
        editor.eye_mode_button.invoke();self.root.update()
        self.assertTrue(self.session.lab.processor.mapping.require_wink)
        provider=Mock();self.session.dictation.provider=provider
        self.ui.setup_dictation()
        provider.start.assert_called_once_with(check=True)
        self.assertFalse(self.session.lab.processor.armed)

    def test_screen_destination_settings_show_only_relevant_response_controls(self):
        self.ui.refresh();self.root.update()
        panel=self.ui.mapping_page
        panel.show_settings();self.root.update()
        self.assertEqual(panel.pointer_mode.get(),'Screen destination')
        self.assertTrue(panel.jitter_widget.winfo_ismapped())
        self.assertTrue(all(widget.winfo_ismapped() for widget in panel.target_widgets))
        self.assertEqual(panel.target_fields['target_smoothing_ms'].get(),'20')
        self.assertEqual(panel.down_gain.get(),'4')
        self.assertFalse(panel.pointer_widgets['smoothing_ms'][1].winfo_ismapped())
        self.assertFalse(panel.pointer_widgets['deadzone'][1].winfo_ismapped())
        panel.pointer_mode.set('Relative movement');panel.pointer_controls();self.root.update()
        self.assertFalse(panel.jitter_widget.winfo_ismapped())
        self.assertTrue(all(not widget.winfo_ismapped() for widget in panel.target_widgets))
        self.assertTrue(panel.pointer_widgets['deadzone'][1].winfo_ismapped())
        panel._apply();self.ui.refresh();self.root.update()
        self.assertEqual(self.session.lab.state()['mapping']['pointer_mode'],'velocity')
        panel.pointer_mode.set('Screen destination');panel.target_jitter.set('.015')
        panel.target_fields['target_smoothing_ms'].set('12')
        panel.down_gain.set('5');panel._apply()
        state=self.session.lab.state()
        self.assertEqual(state['message']['pointer'],dict(mode='target',x=.5,y=.5,speed=0))
        self.assertEqual(state['mapping']['target_jitter'],.015)
        self.assertEqual(self.session.lab.processor.pointer.config.smoothing_ms,12)
        self.assertEqual(state['mapping']['pointer_down_gain'],5)
        self.assertFalse(state['snapshot']['armed'])

    def test_two_tabs_mapping_rows_and_pointer_settings_share_signals(self):
        from Vision.mouse_demo import mouse_demo_records
        from Processing.mappings.demo import gaming_demo_frame
        frame = next(mouse_demo_records(count=1))
        frame['timestamp_ms'] = self.session.clock()
        self.session.deliver(gaming_demo_frame(frame,30))
        self.ui.refresh()
        self.root.geometry('1280x850')
        self.root.update()
        self.assertEqual([self.ui.notebook.tab(t,'text') for t in self.ui.notebook.tabs()],['Signals','Calibration'])
        panel = self.ui.mapping_page
        self.assertEqual(len(panel.table.get_children()),8)
        self.assertTrue(panel.table.winfo_ismapped())
        self.assertGreaterEqual(self.ui.raw_canvas.winfo_height(),160)
        self.assertTrue(self.ui.error_label.winfo_ismapped())
        self.assertLess(self.ui.error_label.winfo_rooty(),self.root.winfo_rooty()+self.root.winfo_height())
        last_row = panel.table.bbox('pupil_y')
        self.assertTrue(last_row)
        self.assertLessEqual(last_row[1]+last_row[3],panel.table.winfo_height())
        self.assertFalse(panel.settings_window.winfo_ismapped())
        panel.show_settings()
        self.root.update()
        self.assertTrue(panel.settings_window.winfo_ismapped())
        self.session.lab.processor.armed = True
        panel.pointer_fields['deadzone'].set('.22')
        panel.fields[('head_y','activation')].set('.4')
        panel.apply()
        self.assertEqual(self.session.lab.state()['config']['pointer']['deadzone'],.22)
        self.assertEqual(self.session.lab.state()['mapping']['head_y']['activation'],.4)
        self.assertFalse(self.session.lab.processor.armed)
        panel.pointer_fields['deadzone'].set('bad')
        self.ui.guarded(panel.apply)
        self.assertIn('bad',panel.settings_notice.get())
        self.assertEqual(self.session.lab.state()['config']['pointer']['deadzone'],.22)

    def test_loading_camera_profile_while_stopped_selects_camera_without_opening_it(self):
        with patch.object(self.session,'_camera') as camera:
            self.load(self.profile())
            self.root.update()
            camera.assert_not_called()
        self.assertEqual(self.session.mode,'camera')
        self.assertIn('left',self.session.detector_runtime.workbench.eyes)
        self.assertEqual(self.ui.source_var.get(),self.ui.source_name('camera'))
        self.assertFalse(self.session.lab.processor.armed)
        self.assertTrue(self.session.state()['profile_bound'])

    def test_loading_profile_from_running_demo_starts_matching_camera_with_fits(self):
        path = self.profile()
        opened = threading.Event()
        def camera(*args):
            opened.set()
            self.session.stop_event.wait(3)
        with patch.object(self.session,'_camera',side_effect=camera):
            self.session.start('demo')
            self.load(path)
            self.until(opened.is_set)
            self.assertEqual(self.session.mode,'camera')
            self.assertIn('left',self.session.detector_runtime.workbench.eyes)
            self.assertTrue(self.session.state()['profile_bound'])
            self.assertFalse(self.session.lab.processor.armed)
            self.ui.stop_source()
            self.session.thread.join(2)

    def test_source_picker_switches_without_second_worker_and_stop_cancels_pending_switch(self):
        old_worker_released = threading.Event()
        old_worker_entered = threading.Event()
        def camera(*args):
            old_worker_entered.set()
            old_worker_released.wait(3)
        with patch.object(self.session,'_camera',side_effect=camera):
            self.session.start('camera',model=self.model)
            self.until(old_worker_entered.is_set)
            old = self.session.thread
            self.ui.source_var.set(self.ui.source_name('demo'))
            self.ui.source_picker.event_generate('<<ComboboxSelected>>')
            self.root.update()
            self.assertIs(self.session.thread,old)
            self.ui.stop_source()
            old_worker_released.set()
            old.join(2)
            self.root.after(100,lambda:None)
            self.root.update()
            self.assertIs(self.session.thread,old)
            self.assertEqual(self.session.mode,'camera')
            self.assertFalse(self.session.lab.processor.armed)

    def test_bad_profile_does_not_stop_running_source_or_clear_fits(self):
        bad = Path(self.directory.name)/'invalid.json'
        bad.write_text('{bad json')
        self.session.start('demo')
        worker = self.session.thread
        self.load(bad)
        self.assertTrue(self.session.state()['running'])
        self.assertIs(self.session.thread,worker)
        self.assertIn('not valid JSON',self.ui.message.get())

    def test_nested_guard_keeps_missing_model_error_visible(self):
        self.ui.source_var.set(self.ui.source_name('camera'))
        self.ui.model_var.set('/missing/face-model.task')
        self.ui.guarded(self.ui.start_source)
        self.assertIn('Camera model not found',self.ui.message.get())
        self.assertFalse(self.session.state()['running'])
