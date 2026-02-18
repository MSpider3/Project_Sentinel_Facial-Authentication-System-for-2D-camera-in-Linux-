/* CameraPreview.vala - Enhanced camera preview with Cairo overlay */

namespace Sentinel {

    public class CameraPreview : Gtk.DrawingArea {
        private Gdk.Pixbuf? current_frame;
        private int[] ? face_box;
        private string status_text = "";
        private double confidence = 0.0;
        private Gdk.RGBA box_color;

        public CameraPreview () {
            // Set up drawing area
            set_content_width (640);
            set_content_height (480);
            set_draw_func (draw_function);

            // Default box color (yellow)
            box_color = Gdk.RGBA ();
            box_color.parse ("#FFD700");
        }

        public void set_frame_from_base64 (string base64_data) {
            try {
                // Decode base64
                uint8[] image_data = Base64.decode (base64_data);

                // Load into pixbuf
                var stream = new MemoryInputStream.from_data (image_data);
                current_frame = new Gdk.Pixbuf.from_stream (stream);

                queue_draw ();
            } catch (Error e) {
                warning ("Failed to load frame: %s", e.message);
            }
        }

        public void set_face_box (int x, int y, int width, int height) {
            face_box = { x, y, width, height };
            queue_draw ();
        }

        public void clear_face_box () {
            face_box = null;
            queue_draw ();
        }

        public void set_status_text (string text) {
            status_text = text;
            queue_draw ();
        }

        public void set_confidence (double conf) {
            confidence = conf;
            queue_draw ();
        }

        public void set_box_color_by_status (string status) {
            box_color = Gdk.RGBA ();

            switch (status) {
            case "SUCCESS" :
            case "RECOGNIZED" :
                box_color.parse ("#00FF00"); // Green
                break;
            case "FAILURE":
                box_color.parse ("#FF0000"); // Red
                break;
            case "REQUIRE_2FA":
                box_color.parse ("#FFA500"); // Orange
                break;
            default:
                box_color.parse ("#FFD700"); // Yellow
                break;
            }

            queue_draw ();
        }

        public void set_box_color_from_string (string color_hex) {
            box_color = Gdk.RGBA ();
            box_color.parse (color_hex);
            queue_draw ();
        }

        private void draw_function (Gtk.DrawingArea da, Cairo.Context cr, int width, int height) {
            // Clear background
            cr.set_source_rgb (0.1, 0.1, 0.1);
            cr.paint ();

            if (current_frame == null) {
                return;
            }

            // Calculate scaling to fit frame in widget
            int frame_width = current_frame.get_width ();
            int frame_height = current_frame.get_height ();

            double scale_x = (double) width / frame_width;
            double scale_y = (double) height / frame_height;
            double scale = double.min (scale_x, scale_y);

            int scaled_width = (int) (frame_width * scale);
            int scaled_height = (int) (frame_height * scale);

            int offset_x = (width - scaled_width) / 2;
            int offset_y = (height - scaled_height) / 2;

            // Draw camera frame
            cr.save ();
            cr.translate (offset_x, offset_y);
            cr.scale (scale, scale);

            Gdk.cairo_set_source_pixbuf (cr, current_frame, 0, 0);
            cr.paint ();

            cr.restore ();

            // Draw face box if present
            if (face_box != null && face_box.length == 4) {
                int box_x = (int) (face_box[0] * scale) + offset_x;
                int box_y = (int) (face_box[1] * scale) + offset_y;
                int box_w = (int) (face_box[2] * scale);
                int box_h = (int) (face_box[3] * scale);

                // Draw rectangle
                cr.set_source_rgba (box_color.red, box_color.green, box_color.blue, 0.8);
                cr.set_line_width (3.0);
                cr.rectangle (box_x, box_y, box_w, box_h);
                cr.stroke ();

                // Draw corner accents (for modern look)
                int corner_len = 20;
                cr.set_line_width (4.0);

                // Top-left
                cr.move_to (box_x, box_y + corner_len);
                cr.line_to (box_x, box_y);
                cr.line_to (box_x + corner_len, box_y);
                cr.stroke ();

                // Top-right
                cr.move_to (box_x + box_w - corner_len, box_y);
                cr.line_to (box_x + box_w, box_y);
                cr.line_to (box_x + box_w, box_y + corner_len);
                cr.stroke ();

                // Bottom-left
                cr.move_to (box_x, box_y + box_h - corner_len);
                cr.line_to (box_x, box_y + box_h);
                cr.line_to (box_x + corner_len, box_y + box_h);
                cr.stroke ();

                // Bottom-right
                cr.move_to (box_x + box_w - corner_len, box_y + box_h);
                cr.line_to (box_x + box_w, box_y + box_h);
                cr.line_to (box_x + box_w, box_y + box_h - corner_len);
                cr.stroke ();

                // Draw confidence percentage if available
                if (confidence > 0.0) {
                    cr.select_font_face ("Sans", Cairo.FontSlant.NORMAL, Cairo.FontWeight.BOLD);
                    cr.set_font_size (16);

                    string conf_text = "%.1f%%".printf (confidence * 100);
                    Cairo.TextExtents extents;
                    cr.text_extents (conf_text, out extents);

                    // Background for text
                    int text_x = box_x + box_w / 2 - (int) (extents.width / 2);
                    int text_y = box_y + box_h + 25;

                    cr.set_source_rgba (0, 0, 0, 0.7);
                    cr.rectangle (
                                  text_x - 5,
                                  text_y - extents.height - 5,
                                  extents.width + 10,
                                  extents.height + 10
                    );
                    cr.fill ();

                    // Text
                    cr.set_source_rgba (box_color.red, box_color.green, box_color.blue, 1.0);
                    cr.move_to (text_x, text_y);
                    cr.show_text (conf_text);
                }
            }

            // Draw status text at top
            if (status_text != "") {
                cr.select_font_face ("Sans", Cairo.FontSlant.NORMAL, Cairo.FontWeight.BOLD);
                cr.set_font_size (20);

                Cairo.TextExtents extents;
                cr.text_extents (status_text, out extents);

                int text_x = width / 2 - (int) (extents.width / 2);
                int text_y = 30;

                // Background
                cr.set_source_rgba (0, 0, 0, 0.7);
                cr.rectangle (
                              text_x - 10,
                              text_y - extents.height - 5,
                              extents.width + 20,
                              extents.height + 15
                );
                cr.fill ();

                // Text
                cr.set_source_rgb (1.0, 1.0, 1.0);
                cr.move_to (text_x, text_y);
                cr.show_text (status_text);
            }
        }
    }
} // namespace Sentinel