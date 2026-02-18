/* MainWindow.vala - Main application window with tab navigation */

namespace Sentinel {

    public class MainWindow : Gtk.ApplicationWindow {
        private BackendService backend;
        private Gtk.Stack stack;
        private AuthView auth_view;
        private EnrollView enroll_view;

        public MainWindow (Gtk.Application app) {
            Object (application: app);

            title = "Project Sentinel";
            default_width = 1000;
            default_height = 700;

            backend = new BackendService ();
            backend.error_occurred.connect (on_backend_error);

            setup_ui ();
            initialize_backend.begin ();
        }

        private void setup_ui () {
            // Header bar
            var header = new Gtk.HeaderBar ();
            set_titlebar (header);

            // Stack switcher
            var stack_switcher = new Gtk.StackSwitcher ();
            stack_switcher.halign = Gtk.Align.CENTER;
            header.set_title_widget (stack_switcher);

            // Main stack
            stack = new Gtk.Stack ();
            stack.transition_type = Gtk.StackTransitionType.SLIDE_LEFT_RIGHT;
            stack_switcher.stack = stack;

            // Authentication view
            auth_view = new AuthView (backend);
            stack.add_titled (auth_view, "auth", "Authenticate");

            // Enrollment view
            enroll_view = new EnrollView (backend);
            stack.add_titled (enroll_view, "enroll", "Enroll");

            set_child (stack);

            // Apply styling
            var css_provider = new Gtk.CssProvider ();
            // Try loading from local path (development) or install path
            // For now, assuming running from project root
            var css_file = File.new_for_path ("src/style.css");
            css_provider.load_from_file (css_file);


            // Add CSS provider to display
            Gtk.StyleContext.add_provider_for_display (
                                                       Gdk.Display.get_default (),
                                                       css_provider,
                                                       Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            );
        }

        private async void initialize_backend () {
            if (!yield backend.start ()) {
                var dialog = new Gtk.AlertDialog ("Failed to start backend service");
                dialog.show (this);
                return;
            }

            var result = yield backend.call_method ("initialize");

            if (result == null) {
                var dialog = new Gtk.AlertDialog ("Failed to initialize backend");
                dialog.show (this);
                return;
            }

            var result_obj = result.get_object ();
            if (!result_obj.get_boolean_member ("success")) {
                var error = result_obj.get_string_member ("error");
                var dialog = new Gtk.AlertDialog ("Initialization error: %s".printf (error));
                dialog.show (this);
            } else {
                // Backend ready
                auth_view.on_backend_ready ();
                auth_view.refresh_users.begin ();
            }
        }

        private void on_backend_error (string error) {
            var dialog = new Gtk.AlertDialog ("Backend error: %s".printf (error));
            dialog.show (this);
        }

        public override void dispose () {
            backend.stop ();
            base.dispose ();
        }
    }
} // namespace Sentinel