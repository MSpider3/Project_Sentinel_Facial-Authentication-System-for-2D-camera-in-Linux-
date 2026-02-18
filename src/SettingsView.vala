/* SettingsView.vala - Configuration UI for Project Sentinel */

namespace Sentinel {

    public class SettingsView : Gtk.Box {
        private BackendService backend;
        private Gtk.SpinButton camera_width_spin;
        private Gtk.SpinButton camera_height_spin;
        private Gtk.SpinButton camera_fps_spin;
        private Gtk.Scale golden_threshold_scale;
        private Gtk.Scale standard_threshold_scale;
        private Gtk.Scale twofa_threshold_scale;
        private Gtk.Scale spoof_threshold_scale;
        private Gtk.SpinButton challenge_timeout_spin;
        private Gtk.Switch blink_detection_switch;

        public SettingsView (BackendService backend) {
            Object (orientation: Gtk.Orientation.VERTICAL, spacing: 12);

            this.backend = backend;

            setup_ui ();
            load_configuration.begin ();
        }

        private void setup_ui () {
            set_margin_top (12);
            set_margin_bottom (12);
            set_margin_start (12);
            set_margin_end (12);

            // Header
            var title = new Gtk.Label ("<b>Configuration</b>");
            title.use_markup = true;
            title.halign = Gtk.Align.START;
            append (title);

            append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));

            // Create scrolled window for settings
            var scrolled = new Gtk.ScrolledWindow ();
            scrolled.vexpand = true;

            var settings_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 20);
            scrolled.set_child (settings_box);
            append (scrolled);

            // Camera Settings
            settings_box.append (create_section_header ("Camera Settings"));
            settings_box.append (create_camera_settings ());

            // Security Thresholds
            settings_box.append (create_section_header ("Security Thresholds"));
            settings_box.append (create_security_settings ());

            // Liveness Detection
            settings_box.append (create_section_header ("Liveness Detection"));
            settings_box.append (create_liveness_settings ());

            // Buttons
            var button_box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            button_box.halign = Gtk.Align.CENTER;

            var save_button = new Gtk.Button.with_label ("Save Configuration");
            save_button.add_css_class ("suggested-action");
            save_button.clicked.connect (on_save_clicked);
            button_box.append (save_button);

            var reset_button = new Gtk.Button.with_label ("Reset to Defaults");
            reset_button.clicked.connect (on_reset_clicked);
            button_box.append (reset_button);

            append (button_box);
        }

        private Gtk.Widget create_section_header (string title) {
            var label = new Gtk.Label ("<b>%s</b>".printf (title));
            label.use_markup = true;
            label.halign = Gtk.Align.START;
            label.add_css_class ("title-3");
            return label;
        }

        private Gtk.Widget create_camera_settings () {
            var grid = new Gtk.Grid ();
            grid.column_spacing = 12;
            grid.row_spacing = 6;

            int row = 0;

            // Resolution Width
            grid.attach (new Gtk.Label ("Resolution Width:"), 0, row, 1, 1);
            camera_width_spin = new Gtk.SpinButton.with_range (320, 1920, 1);
            camera_width_spin.value = 640;
            grid.attach (camera_width_spin, 1, row, 1, 1);
            row++;

            // Resolution Height
            grid.attach (new Gtk.Label ("Resolution Height:"), 0, row, 1, 1);
            camera_height_spin = new Gtk.SpinButton.with_range (240, 1080, 1);
            camera_height_spin.value = 480;
            grid.attach (camera_height_spin, 1, row, 1, 1);
            row++;

            // FPS
            grid.attach (new Gtk.Label ("FPS:"), 0, row, 1, 1);
            camera_fps_spin = new Gtk.SpinButton.with_range (5, 60, 1);
            camera_fps_spin.value = 15;
            grid.attach (camera_fps_spin, 1, row, 1, 1);

            return grid;
        }

        private Gtk.Widget create_security_settings () {
            var grid = new Gtk.Grid ();
            grid.column_spacing = 12;
            grid.row_spacing = 12;

            int row = 0;

            // Golden Threshold
            grid.attach (new Gtk.Label ("Golden Zone Threshold (0.0 - 1.0):"), 0, row, 1, 1);
            golden_threshold_scale = new Gtk.Scale.with_range (Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01);
            golden_threshold_scale.set_value (0.25);
            golden_threshold_scale.set_draw_value (true);
            golden_threshold_scale.hexpand = true;
            grid.attach (golden_threshold_scale, 1, row, 1, 1);
            row++;

            // Standard Threshold
            grid.attach (new Gtk.Label ("Standard Zone Threshold:"), 0, row, 1, 1);
            standard_threshold_scale = new Gtk.Scale.with_range (Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01);
            standard_threshold_scale.set_value (0.42);
            standard_threshold_scale.set_draw_value (true);
            standard_threshold_scale.hexpand = true;
            grid.attach (standard_threshold_scale, 1, row, 1, 1);
            row++;

            // 2FA Threshold
            grid.attach (new Gtk.Label ("Two-Factor Auth Threshold:"), 0, row, 1, 1);
            twofa_threshold_scale = new Gtk.Scale.with_range (Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01);
            twofa_threshold_scale.set_value (0.50);
            twofa_threshold_scale.set_draw_value (true);
            twofa_threshold_scale.hexpand = true;
            grid.attach (twofa_threshold_scale, 1, row, 1, 1);
            row++;

            // Spoof Threshold
            grid.attach (new Gtk.Label ("Anti-Spoof Threshold:"), 0, row, 1, 1);
            spoof_threshold_scale = new Gtk.Scale.with_range (Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01);
            spoof_threshold_scale.set_value (0.92);
            spoof_threshold_scale.set_draw_value (true);
            spoof_threshold_scale.hexpand = true;
            grid.attach (spoof_threshold_scale, 1, row, 1, 1);

            return grid;
        }

        private Gtk.Widget create_liveness_settings () {
            var grid = new Gtk.Grid ();
            grid.column_spacing = 12;
            grid.row_spacing = 6;

            int row = 0;

            // Challenge Timeout
            grid.attach (new Gtk.Label ("Challenge Timeout (seconds):"), 0, row, 1, 1);
            challenge_timeout_spin = new Gtk.SpinButton.with_range (5, 60, 1);
            challenge_timeout_spin.value = 20;
            grid.attach (challenge_timeout_spin, 1, row, 1, 1);
            row++;

            // Blink Detection
            grid.attach (new Gtk.Label ("Enable Blink Detection:"), 0, row, 1, 1);
            blink_detection_switch = new Gtk.Switch ();
            blink_detection_switch.active = true;
            grid.attach (blink_detection_switch, 1, row, 1, 1);

            return grid;
        }

        private async void load_configuration () {
            var result = yield backend.call_method ("get_config");

            if (result == null) {
                return;
            }

            try {
                var result_obj = result.get_object ();
                if (!result_obj.get_boolean_member ("success")) {
                    return;
                }

                var config = result_obj.get_object_member ("config");

                // Load camera settings
                if (config.has_member ("camera_width")) {
                    camera_width_spin.value = config.get_int_member ("camera_width");
                }
                if (config.has_member ("camera_height")) {
                    camera_height_spin.value = config.get_int_member ("camera_height");
                }
                if (config.has_member ("camera_fps")) {
                    camera_fps_spin.value = config.get_int_member ("camera_fps");
                }

                // Load thresholds
                if (config.has_member ("golden_threshold")) {
                    golden_threshold_scale.set_value (config.get_double_member ("golden_threshold"));
                }
                if (config.has_member ("standard_threshold")) {
                    standard_threshold_scale.set_value (config.get_double_member ("standard_threshold"));
                }
                if (config.has_member ("twofa_threshold")) {
                    twofa_threshold_scale.set_value (config.get_double_member ("twofa_threshold"));
                }
                if (config.has_member ("spoof_threshold")) {
                    spoof_threshold_scale.set_value (config.get_double_member ("spoof_threshold"));
                }

                // Load liveness settings
                if (config.has_member ("challenge_timeout")) {
                    challenge_timeout_spin.value = config.get_double_member ("challenge_timeout");
                }
            } catch (Error e) {
                warning ("Failed to load configuration: %s", e.message);
            }
        }

        private void on_save_clicked () {
            save_configuration.begin ();
        }

        private async void save_configuration () {
            var params = new Json.Object ();
            var config = new Json.Object ();

            // Camera settings
            config.set_int_member ("camera_width", (int) camera_width_spin.value);
            config.set_int_member ("camera_height", (int) camera_height_spin.value);
            config.set_int_member ("camera_fps", (int) camera_fps_spin.value);

            // Security thresholds
            config.set_double_member ("golden_threshold", golden_threshold_scale.get_value ());
            config.set_double_member ("standard_threshold", standard_threshold_scale.get_value ());
            config.set_double_member ("twofa_threshold", twofa_threshold_scale.get_value ());
            config.set_double_member ("spoof_threshold", spoof_threshold_scale.get_value ());

            // Liveness settings
            config.set_double_member ("challenge_timeout", challenge_timeout_spin.value);
            config.set_boolean_member ("blink_detection", blink_detection_switch.active);

            params.set_object_member ("config", config);

            var result = yield backend.call_method ("update_config", params);

            if (result != null) {
                var dialog = new Gtk.AlertDialog ("Configuration saved successfully!");
                dialog.show (null);
            }
        }

        private void on_reset_clicked () {
            // Reset to defaults
            camera_width_spin.value = 640;
            camera_height_spin.value = 480;
            camera_fps_spin.value = 15;
            golden_threshold_scale.set_value (0.25);
            standard_threshold_scale.set_value (0.42);
            twofa_threshold_scale.set_value (0.50);
            spoof_threshold_scale.set_value (0.92);
            challenge_timeout_spin.value = 20;
            blink_detection_switch.active = true;
        }
    }
} // namespace Sentinel