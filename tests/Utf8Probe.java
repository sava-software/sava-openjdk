import java.io.Console;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/** Regression probe for native UTF-8 decoding in the published and exported runtimes. */
public final class Utf8Probe {
    private static final String UNICODE = "caf\u00e9-\u20ac-\uD83D\uDE80-\uFFFD";
    private static final String ASCII = "plain-ASCII-123";

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void requireUtf8(String property) {
        String value = System.getProperty(property);
        if (value == null || !Charset.forName(value).equals(StandardCharsets.UTF_8)) {
            System.err.println("UTF8_PROBE_ENCODING_FAILURE");
            System.exit(42);
        }
    }

    public static void main(String[] args) {
        requireUtf8("native.encoding");
        requireUtf8("sun.jnu.encoding");
        require(UNICODE.equals(System.getenv("UTF8_PROBE_TEXT")), "Unicode environment decoding failed");
        require(ASCII.equals(System.getenv("UTF8_PROBE_ASCII")), "ASCII environment decoding failed");
        require(args.length == 1, "Expected one probe mode");

        if (!args[0].equals("environment")) {
            require(args[0].equals("console-unicode") || args[0].equals("console-ascii"), "Unknown probe mode");
            Console console = System.console();
            require(console != null, "A controlling terminal is required");
            char[] expected = (args[0].equals("console-unicode") ? UNICODE : ASCII).toCharArray();
            char[] actual = console.readPassword("PASSWORD_READY%n");
            try {
                require(Arrays.equals(expected, actual), "Console password decoding failed");
            } finally {
                Arrays.fill(expected, '\0');
                if (actual != null) {
                    Arrays.fill(actual, '\0');
                }
            }
        }
        System.out.println("UTF8_PROBE_OK");
    }
}
