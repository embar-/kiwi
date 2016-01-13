from nose.tools import *
from mock import patch
from mock import call
import mock
import kiwi

import nose_helper

from kiwi.exceptions import *
from kiwi.live_image_builder import LiveImageBuilder


class TestLiveImageBuilder(object):
    def setup(self):
        self.firmware = mock.Mock()
        self.firmware.efi_mode = mock.Mock(
            return_value=True
        )
        kiwi.live_image_builder.FirmWare = mock.Mock(
            return_value=self.firmware
        )
        self.boot_image_task = mock.Mock()
        self.boot_image_task.boot_root_directory = 'initrd_dir'
        self.boot_image_task.initrd_filename = 'initrd'
        kiwi.live_image_builder.BootImageTask = mock.Mock(
            return_value=self.boot_image_task
        )
        self.mbrid = mock.Mock()
        self.mbrid.get_id = mock.Mock(
            return_value='0xffffffff'
        )
        kiwi.live_image_builder.ImageIdentifier = mock.Mock(
            return_value=self.mbrid
        )
        kiwi.live_image_builder.Path = mock.Mock()
        self.kernel = mock.Mock()
        self.kernel.get_kernel = mock.Mock()
        self.kernel.get_xen_hypervisor = mock.Mock()
        self.kernel.copy_kernel = mock.Mock()
        self.kernel.copy_xen_hypervisor = mock.Mock()
        kiwi.live_image_builder.Kernel = mock.Mock(
            return_value=self.kernel
        )
        self.xml_state = mock.Mock()
        self.xml_state.build_type.get_flags = mock.Mock(
            return_value=None
        )
        self.xml_state.get_image_version = mock.Mock(
            return_value='1.2.3'
        )
        self.xml_state.xml_data.get_name = mock.Mock(
            return_value='result-image'
        )
        self.xml_state.build_type.get_volid = mock.Mock(
            return_value='volid'
        )
        self.xml_state.build_type.get_kernelcmdline = mock.Mock(
            return_value='custom_cmdline'
        )
        self.live_image = LiveImageBuilder(
            self.xml_state, 'target_dir', 'source_dir'
        )
        self.live_image.machine = mock.Mock()
        self.live_image.machine.get_domain = mock.Mock(
            return_value='dom0'
        )
        self.result = mock.Mock()
        self.live_image.result = self.result
        self.live_image.hybrid = True

    @patch('kiwi.live_image_builder.mkdtemp')
    @patch('kiwi.live_image_builder.Command.run')
    @patch('kiwi.live_image_builder.Iso.create_hybrid')
    @patch('kiwi.live_image_builder.FileSystemSquashFs')
    @patch('kiwi.live_image_builder.FileSystemIsoFs')
    @patch('kiwi.live_image_builder.BootLoaderConfig')
    def test_create_overlay_structure(
        self, mock_bootloader, mock_isofs, mock_squashfs,
        mock_hybrid, mock_command, mock_dtemp
    ):
        tmpdir_name = ['temp-squashfs', 'temp_media_dir']

        def side_effect(prefix, dir):
            return tmpdir_name.pop()

        mock_dtemp.side_effect = side_effect
        self.live_image.live_type = 'overlay'
        squashed_image = mock.Mock()
        mock_squashfs.return_value = squashed_image
        bootloader = mock.Mock()
        mock_bootloader.return_value = bootloader
        iso_image = mock.Mock()
        iso_image.create_on_file.return_value = 'offset'
        mock_isofs.return_value = iso_image

        self.live_image.create()

        self.live_image.boot_image_task.prepare.assert_called_once_with()
        mock_squashfs.assert_called_once_with(
            device_provider=None, source_dir='source_dir'
        )
        squashed_image.create_on_file.assert_called_once_with(
            'target_dir/result-image-read-only.x86_64-1.2.3'
        )
        assert mock_command.call_args_list[0] == call(
            [
                'mv', 'target_dir/result-image-read-only.x86_64-1.2.3',
                'temp_media_dir'
            ]
        )
        assert mock_bootloader.call_args_list[0] == call(
            'isolinux', self.xml_state, 'temp_media_dir'
        )
        assert bootloader.setup_live_boot_images.call_args_list[0] == call(
            lookup_path=self.live_image.boot_image_task.boot_root_directory,
            mbrid=None
        )
        assert bootloader.setup_live_image_config.call_args_list[0] == call(
            mbrid=None
        )
        assert bootloader.write.call_args_list[0] == call()

        assert mock_bootloader.call_args_list[1] == call(
            'grub2', self.xml_state, 'temp_media_dir'
        )
        assert bootloader.setup_live_boot_images.call_args_list[1] == call(
            lookup_path=self.live_image.boot_image_task.boot_root_directory,
            mbrid=self.mbrid
        )
        assert bootloader.setup_live_image_config.call_args_list[1] == call(
            mbrid=self.mbrid
        )
        assert bootloader.write.call_args_list[1] == call()

        self.boot_image_task.create_initrd.assert_called_once_with(
            self.mbrid
        )
        self.kernel.copy_kernel.assert_called_once_with(
            'temp_media_dir/boot/x86_64/loader', '/linux'
        )
        self.kernel.copy_xen_hypervisor.assert_called_once_with(
            'temp_media_dir/boot/x86_64/loader', '/xen.gz'
        )
        assert mock_command.call_args_list[1] == call(
            ['mv', 'initrd', 'temp_media_dir/boot/x86_64/loader/initrd']
        )
        mock_isofs.assert_called_once_with(
            custom_args=[
                '-A', '0xffffffff',
                '-allow-limited-size',
                '-udf', '-p', '"KIWI - http://suse.github.com/kiwi"',
                '-publisher', '"SUSE LINUX GmbH"',
                '-V', '"volid"'
            ], device_provider=None, source_dir='temp_media_dir'
        )
        iso_image.create_on_file.assert_called_once_with(
            'target_dir/result-image.iso'
        )
        mock_hybrid.assert_called_once_with(
            'offset', self.mbrid, 'target_dir/result-image.iso'
        )
        self.result.add.assert_called_once_with(
            'live_image', 'target_dir/result-image.iso'
        )

    @patch('kiwi.live_image_builder.mkdtemp')
    @patch('kiwi.live_image_builder.Command.run')
    @raises(KiwiLiveBootImageError)
    def test_create_invalid_iso_structure(self, mock_command, mock_dtemp):
        self.live_image.live_type = 'bogus'
        self.live_image.create()

    @raises(KiwiLiveBootImageError)
    def test_create_no_boot_task(self):
        self.live_image.boot_image_task.required = mock.Mock(
            return_value=False
        )
        self.live_image.create()

    @patch('kiwi.live_image_builder.mkdtemp')
    @patch('kiwi.live_image_builder.Command.run')
    @patch('kiwi.live_image_builder.BootLoaderConfig')
    @raises(KiwiLiveBootImageError)
    def test_create_no_kernel_found(self, mock_boot, mock_command, mock_dtemp):
        self.kernel.get_kernel.return_value = False
        self.live_image.create()

    @patch('kiwi.live_image_builder.mkdtemp')
    @patch('kiwi.live_image_builder.Command.run')
    @patch('kiwi.live_image_builder.BootLoaderConfig')
    @raises(KiwiLiveBootImageError)
    def test_create_no_hypervisor_found(
        self, mock_boot, mock_command, mock_dtemp
    ):
        self.kernel.get_xen_hypervisor.return_value = False
        self.live_image.create()

    @patch('kiwi.live_image_builder.Path.wipe')
    def test_destructor(self, mock_wipe):
        self.live_image.media_dir = 'media-dir'
        self.live_image.__del__()
        assert mock_wipe.call_args_list == [
            call('media-dir')
        ]
        self.live_image.media_dir = None
