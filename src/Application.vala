/* Application.vala - Main application entry point for Project Sentinel */

namespace Sentinel {

public class Application : Gtk.Application {
    public Application () {
        Object (
            application_id: "com.projectsentinel.ui",
            flags: ApplicationFlags.FLAGS_NONE
        );
    }

    protected override void activate () {
        var win = new MainWindow (this);
        win.present ();
    }

    public static int main (string[] args) {
        var app = new Application ();
        return app.run (args);
    }
}

} // namespace Sentinel
