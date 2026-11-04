from dataclasses import replace
from pathlib import Path
import time

from louasfm_camera.config import ConfigStore
from louasfm_camera.models import CameraSettings
from louasfm_camera.services.acquisition import AcquisitionService
from louasfm_camera.ui.main_window import MainWindow


def test_worker_external_recording_snapshot_and_graceful_drain(tmp_path, wait):
    service = AcquisitionService('simulated')
    errors = []
    states = []
    service.error.connect(errors.append)
    service.state_changed.connect(states.append)
    settings = CameraSettings(width=64,height=48,trigger_mode='external')
    output = {'directory':str(tmp_path),'prefix':'test','image_format':'TIFF'}
    try:
        service.command('connect',backend='simulated',settings=settings)
        wait(lambda: states and states[-1]=='idle')
        service.command('start',settings=settings,output=output,record=True)
        wait(lambda: states[-1]=='recording')
        assert service.preview() is None
        for _ in range(3):
            service.command('simulate_external')
        wait(lambda: service.counts()[1]==3)
        service.command('stop')
        wait(lambda: states[-1]=='idle')
        service.command('snap',output=output)
        wait(lambda: service.counts()[1]==4 and states[-1]=='idle')
        assert service.settings.trigger_mode=='external'
        assert service.preview().metadata['settings']['trigger_mode']=='software'
        service.request_close()
        assert service.wait_closed(5)
        assert len(list(tmp_path.glob('*.tiff')))==4
        assert len(list(tmp_path.glob('*.json')))==4
        assert not errors
    finally:
        service.request_close()
        assert service.wait_closed(5)


def test_running_external_snapshot_waits_for_real_impulse(tmp_path,wait):
    service=AcquisitionService('simulated')
    states=[]
    errors=[]
    service.state_changed.connect(states.append)
    service.error.connect(errors.append)
    settings=CameraSettings(width=32,height=24,trigger_mode='external')
    output={'directory':str(tmp_path),'prefix':'external','image_format':'PNG'}
    try:
        service.command('connect',backend='simulated',settings=settings)
        wait(lambda: states and states[-1]=='idle')
        service.command('start',settings=settings,output=output,record=False)
        wait(lambda: states[-1]=='streaming')
        service.command('snap',output=output)
        wait(lambda: service.pending_save)
        time.sleep(0.05)
        assert service.counts()==(0,0)
        service.command('simulate_external')
        wait(lambda: service.counts()[1]==1)
        assert service.streaming
        assert service.actual_settings.trigger_mode=='external'
        assert not errors
    finally:
        service.request_close()
        assert service.wait_closed(5)


def test_camera_command_failure_closes_partial_configuration(wait):
    service=AcquisitionService('simulated')
    errors=[]
    states=[]
    service.error.connect(errors.append)
    service.state_changed.connect(states.append)
    try:
        service.command('connect',backend='simulated',settings=CameraSettings(width=32,height=24))
        wait(lambda: states and states[-1]=='idle')
        service.command('apply',settings=CameraSettings(width=99999))
        wait(lambda: errors)
        assert states[-1]=='disconnected'
        assert service.camera is None
    finally:
        service.request_close()
        assert service.wait_closed(5)


def test_full_gui_demo_save_pulse_plot_and_settings_restart(tmp_path,wait):
    store=ConfigStore(tmp_path/'state/settings.json')
    config=store.load()
    config['backend']='simulated'
    config['camera']['width']=80
    config['camera']['height']=60
    config['recording']['directory']=str(tmp_path/'images')
    window=MainWindow(store,config)
    try:
        window.show()
        window.connect_camera()
        wait(lambda: window.state=='idle')
        window.camera.fields['exposure_us'].setValue(2500)
        window.apply_camera()
        wait(lambda: window.service.settings.exposure_us==2500)
        window.issue('snap',output=window.output())
        wait(lambda: window.service.counts()[1]==1 and window.state=='idle')
        window.refresh()
        assert window.image_view.current.pixels.shape==(60,80)
        assert 'max=' in window.image_view.statistics.text()
        window.image_view.use_roi.setChecked(True)
        window.pulse_view.set_scheme({'D2':[[0,1],[200,0],[600,1],[900,0]],'S0':[[0,0],[400,1]]},{'D2':'Camera'})
        window.board_channel.setCurrentText('D2')
        assert '0, 600' in window.pulse_view.summary.text()
        assert store.load()['beaglebone']['channel']=='D2'
        assert store.load()['camera']['exposure_us']==2500
        screenshot=tmp_path/'demo.png'
        assert window.grab().save(str(screenshot))
        assert screenshot.stat().st_size>10000
        assert Path(window.latest_path).exists()
        window.close()
        wait(lambda: not window.isVisible())
        assert not window.service.thread.is_alive()
        assert not window.service.writer.thread.is_alive()
        assert store.load()['camera']['trigger_mode']=='external'
    finally:
        window.close()
        wait(lambda: not window.service.thread.is_alive())


def test_free_run_preview_latest_slot_is_bounded(tmp_path,wait):
    service=AcquisitionService('simulated')
    states=[]
    service.state_changed.connect(states.append)
    settings=replace(CameraSettings(),trigger_mode='free',width=32,height=24,frame_rate=50)
    try:
        service.command('connect',backend='simulated',settings=settings)
        wait(lambda: states and states[-1]=='idle')
        service.command('start',settings=settings,output={'directory':str(tmp_path),'image_format':'PNG','prefix':'free'},record=False)
        wait(lambda: service.counts()[0]>=5)
        assert service.preview() is not None
        assert service.writer.queue.qsize()==0
        assert service.counts()[1]==0
    finally:
        service.request_close()
        assert service.wait_closed(5)


def test_rejected_duplicate_start_does_not_interrupt_recording(tmp_path,wait):
    service=AcquisitionService('simulated')
    errors=[]
    states=[]
    service.error.connect(errors.append)
    service.state_changed.connect(states.append)
    settings=CameraSettings(width=32,height=24)
    output={'directory':str(tmp_path),'image_format':'TIFF','prefix':'duplicate'}
    try:
        service.command('connect',backend='simulated',settings=settings)
        wait(lambda: states and states[-1]=='idle')
        service.command('start',settings=settings,output=output,record=True)
        wait(lambda: states[-1]=='recording')
        service.command('start',settings=settings,output=output,record=True)
        wait(lambda: errors)
        assert service.streaming and service.recording and service.camera is not None
        service.command('simulate_external')
        wait(lambda: service.counts()[1]==1)
    finally:
        service.request_close()
        assert service.wait_closed(5)


def test_disk_error_stops_recording(tmp_path,wait):
    occupied=tmp_path/'not-directory'
    occupied.write_text('occupied')
    service=AcquisitionService('simulated')
    errors=[]
    states=[]
    service.error.connect(errors.append)
    service.state_changed.connect(states.append)
    settings=CameraSettings(width=32,height=24)
    try:
        service.command('connect',backend='simulated',settings=settings)
        wait(lambda: states and states[-1]=='idle')
        service.command('start',settings=settings,output={'directory':str(occupied),'image_format':'TIFF','prefix':'error'},record=True)
        wait(lambda: states[-1]=='recording')
        service.command('simulate_external')
        wait(lambda: errors and states[-1]=='idle')
        assert not service.streaming
        assert service.counts()[1]==0
    finally:
        service.request_close()
        assert service.wait_closed(5)
