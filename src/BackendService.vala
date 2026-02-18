/* BackendService.vala - JSON-RPC client for Sentinel daemon (Unix socket) */

namespace Sentinel {

    public class BackendService : Object {
        private SocketConnection? connection;
        private DataInputStream? stdout_stream; // input from daemon
        private DataOutputStream? stdin_stream; // output to daemon
        private uint request_id = 1;
        private bool ipc_busy = false;
        private string socket_path;

        public signal void error_occurred (string error);

        public BackendService () {
            // Allow override for dev/testing
            socket_path = Environment.get_variable ("SENTINEL_SOCKET_PATH");
            if (socket_path == null || socket_path.length == 0) {
                socket_path = "/run/sentinel/sentinel.sock";
            }
        }

        private async void sleep_ms (uint ms) {
            Timeout.add (ms, () => { sleep_ms.callback (); return Source.REMOVE; });
            yield;
        }

        private async bool acquire_ipc (double timeout_sec = 10.0) {
            if (!ipc_busy) {
                ipc_busy = true;
                return true;
            }

            Timer t = new Timer ();
            t.start ();

            while (ipc_busy) {
                if (t.elapsed () > timeout_sec) {
                    return false;
                }
                yield sleep_ms (5);
            }
            ipc_busy = true;
            return true;
        }

        private void release_ipc () {
            ipc_busy = false;
        }

        public async bool start () {
            // Connect to the daemon socket (retry briefly to handle boot/restart races)
            var client = new SocketClient ();
            var address = new UnixSocketAddress (socket_path);

            Error? last_err = null;
            for (int i = 0; i < 10; i++) {
                try {
                    connection = yield client.connect_async (address, null);

                    last_err = null;
                    break;
                } catch (Error e) {
                    last_err = e;
                    yield sleep_ms (200);
                }
            }

            if (connection == null) {
                var msg = (last_err != null) ? last_err.message : "unknown error";
                // Only error if we actually failed after retries
                error_occurred ("Could not connect to Sentinel Service. Is the daemon running?\n\nError: %s".printf (msg));
                return false;
            }

            stdin_stream = new DataOutputStream (connection.get_output_stream ());
            stdout_stream = new DataInputStream (connection.get_input_stream ());
            return true;
        }

        public async Json.Node? call_method (string method, Json.Object ? params = null) {
            if (connection == null || stdin_stream == null || stdout_stream == null) {
                error_occurred ("Backend not started");
                return null;
            }

            // Serialize all IO on this connection to avoid:
            // "stream has outstanding operation"
            double acquire_timeout = (method == "initialize") ? 60.0 : 10.0;
            if (!yield acquire_ipc (acquire_timeout)) {
                error_occurred ("IPC busy: timed out waiting to send '%s'".printf (method));
                return null;
            }

            try {
                // Build JSON-RPC request
                var request = new Json.Object ();
                request.set_string_member ("jsonrpc", "2.0");
                request.set_string_member ("method", method);
                int my_id = (int) request_id++;
                request.set_int_member ("id", my_id);

                if (params != null) {
                    request.set_object_member ("params", params);
                } else {
                    request.set_object_member ("params", new Json.Object ());
                }

                var generator = new Json.Generator ();
                var root = new Json.Node (Json.NodeType.OBJECT);
                root.set_object (request);
                generator.set_root (root);

                string request_str = generator.to_data (null) + "\n";

                // Send request
                size_t bytes_written = 0;
                yield stdin_stream.write_all_async (request_str.data, Priority.DEFAULT, null, out bytes_written);

                yield stdin_stream.flush_async ();

                // Read until the response with matching ID arrives
                Timer timer = new Timer ();
                timer.start ();
                double timeout_sec = (method == "initialize") ? 120.0 : 30.0;

                while (true) {
                    if (timer.elapsed () > timeout_sec) {
                        error_occurred ("Backend request '%s' timed out".printf (method));
                        return null;
                    }

                    string? response_line = yield stdout_stream.read_line_async (Priority.DEFAULT, null);

                    if (response_line == null) {
                        error_occurred ("No response from backend (Stream ended)");
                        return null;
                    }

                    response_line = response_line.strip ();
                    if (response_line.length == 0) {
                        continue;
                    }

                    // Only parse lines that look like JSON objects
                    if (!response_line.has_prefix ("{")) {
                        continue;
                    }

                    try {
                        var parser = new Json.Parser ();
                        parser.load_from_data (response_line);
                        var response_root = parser.get_root ();

                        if (response_root == null || response_root.get_node_type () != Json.NodeType.OBJECT) {
                            continue;
                        }

                        var response_obj = response_root.get_object ();

                        // Match response ID
                        if (response_obj.has_member ("id")) {
                            var id_node = response_obj.get_member ("id");
                            if (id_node != null && id_node.get_node_type () != Json.NodeType.NULL) {
                                int resp_id = (int) response_obj.get_int_member ("id");
                                if (resp_id == my_id) {
                                    if (response_obj.has_member ("error")) {
                                        var error_obj = response_obj.get_object_member ("error");
                                        var error_msg = error_obj.has_member ("message") ? error_obj.get_string_member ("message") : "Unknown error";
                                        error_occurred ("Backend error: %s".printf (error_msg));
                                        return null;
                                    }
                                    return response_obj.get_member ("result");
                                }
                            }
                        }

                        // Different ID or notification: ignore and continue
                        continue;
                    } catch (Error e) {
                        continue;
                    }
                }
            } catch (Error e) {
                error_occurred ("RPC error: %s".printf (e.message));
                return null;
            } finally {
                release_ipc ();
            }
        }

        public void stop () {
            if (connection != null) {
                try {
                    connection.close ();
                } catch (Error e) {}
                connection = null;
            }
            stdin_stream = null;
            stdout_stream = null;
        }
    }
} // namespace Sentinel