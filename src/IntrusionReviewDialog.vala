/* IntrusionReviewDialog.vala - Dialog for reviewing detected intrusions */

using Gtk;
using Gdk;
using GLib;
using Json;

namespace Sentinel {

    public class IntrusionReviewDialog : Gtk.Window {
        private BackendService backend;
        private Gtk.Picture image_picture;
        private Gtk.Label info_label;
        private Gtk.Button keep_button;
        private Gtk.Button delete_button;
        private Gtk.ProgressBar progress_bar;

        private string[] intrusion_files;
        private int current_index = 0;

        public signal void review_complete ();

        public IntrusionReviewDialog (Gtk.Window parent, BackendService backend) {
            GLib.Object (
                         transient_for: parent,
                         modal: true,
                         title: "Intrusion Review - Security Alert"
            );

            this.backend = backend;
            set_default_size (500, 600);

            setup_ui ();
            load_intrusions.begin ();
        }

        private void setup_ui () {
            var main_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12);
            main_box.set_margin_top (12);
            main_box.set_margin_bottom (12);
            main_box.set_margin_start (12);
            main_box.set_margin_end (12);
            set_child (main_box);

            // Header
            var header_label = new Gtk.Label ("<b>Suspicious Login Attempts Detected</b>");
            header_label.use_markup = true;
            header_label.add_css_class ("title-2");
            main_box.append (header_label);

            var desc_label = new Gtk.Label (
                                            "While you were away, unauthorized access attempts were detected.\n"
                                            + "Please review each image and decide if it's an intruder or false positive."
            );
            desc_label.wrap = true;
            desc_label.add_css_class ("dim-label");
            main_box.append (desc_label);

            main_box.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));

            // Image display
            image_picture = new Gtk.Picture ();
            image_picture.content_fit = Gtk.ContentFit.CONTAIN;
            image_picture.vexpand = true;
            image_picture.hexpand = true;
            main_box.append (image_picture);

            // Info label
            info_label = new Gtk.Label ("");
            main_box.append (info_label);

            // Progress bar
            progress_bar = new Gtk.ProgressBar ();
            main_box.append (progress_bar);

            main_box.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));

            // Buttons
            var button_box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            button_box.halign = Gtk.Align.CENTER;

            keep_button = new Gtk.Button.with_label ("Keep Blocked (Intruder)");
            keep_button.add_css_class ("destructive-action");
            keep_button.clicked.connect (on_keep_clicked);
            button_box.append (keep_button);

            delete_button = new Gtk.Button.with_label ("Delete (False Positive)");
            delete_button.add_css_class ("suggested-action");
            delete_button.clicked.connect (on_delete_clicked);
            button_box.append (delete_button);

            main_box.append (button_box);
        }

        private async void load_intrusions () {
            var result = yield backend.call_method ("get_intrusions");

            if (result == null) {
                close ();
                return;
            }

            var result_obj = result.get_object ();
            if (!result_obj.get_boolean_member ("success")) {
                close ();
                return;
            }

            var files = result_obj.get_array_member ("files");
            intrusion_files = new string[files.get_length ()];

            for (int i = 0; i < files.get_length (); i++) {
                intrusion_files[i] = files.get_element (i).get_string ();
            }

            if (intrusion_files.length == 0) {
                close ();
                return;
            }

            show_current_image ();
        }

        private void show_current_image () {
            if (current_index >= intrusion_files.length) {
                review_complete ();
                close ();
                return;
            }

            try {
                var file = File.new_for_path (intrusion_files[current_index]);
                var pixbuf = new Gdk.Pixbuf.from_file_at_scale (
                                                                file.get_path (),
                                                                400,
                                                                300,
                                                                true
                );
                image_picture.set_paintable (Gdk.Texture.for_pixbuf (pixbuf));

                info_label.label = "Image %d of %d\n%s".printf (
                                                                current_index + 1,
                                                                intrusion_files.length,
                                                                GLib.Path.get_basename (intrusion_files[current_index])
                );

                progress_bar.fraction = (double) (current_index + 1) / intrusion_files.length;
            } catch (Error e) {
                warning ("Failed to load image: %s", e.message);
                // Skip to next
                current_index++;
                show_current_image ();
            }
        }

        private void on_keep_clicked () {
            confirm_intrusion.begin (intrusion_files[current_index]);
        }

        private async void confirm_intrusion (string filename) {
            var params = new Json.Object ();
            params.set_string_member ("filename", filename);

            var result = yield backend.call_method ("confirm_intrusion", params);

            if (result != null) {
                info ("Confirmed intrusion: %s", filename);
                // Also, we might want to delete the image from display list if we confirm it?
                // Plan says: Keep moves temp embedding to perm playlist.
                // We keep the image for log history?
                // But confusingly we proceed to next image.
            }

            current_index++;
            show_current_image ();
        }

        private void on_delete_clicked () {
            delete_intrusion.begin (intrusion_files[current_index]);
        }

        private async void delete_intrusion (string filename) {
            var params = new Json.Object ();
            params.set_string_member ("filename", filename);

            var result = yield backend.call_method ("delete_intrusion", params);

            if (result != null) {
                info ("Deleted false positive: %s", filename);
            }

            current_index++;
            show_current_image ();
        }
    }
} // namespace Sentinel