import java.io.Console;
import java.io.IOException;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Currency;
import java.util.Locale;

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

    public static void main(String[] args) throws IOException {
        Path tmp = Path.of(System.getProperty("java.io.tmpdir"));
        int mode = (Integer) Files.getAttribute(tmp, "unix:mode");
        require((mode & 07777) == 01777, "Temporary directory must have mode 1777");
        Path temporaryFile = Files.createTempFile(tmp, "utf8-probe-", ".tmp");
        Files.delete(temporaryFile);
        requireUtf8("native.encoding");
        requireUtf8("sun.jnu.encoding");
        require(UNICODE.equals(System.getenv("UTF8_PROBE_TEXT")), "Unicode environment decoding failed");
        require(ASCII.equals(System.getenv("UTF8_PROBE_ASCII")), "ASCII environment decoding failed");
        require(args.length == 1, "Expected one probe mode");
        boolean usLocale = args[0].equals("locale-us");
        Locale expectedLocale = usLocale ? Locale.US : Locale.ENGLISH;
        require(Locale.getDefault().equals(expectedLocale), "Unexpected default Java locale");
        require(Locale.getDefault(Locale.Category.FORMAT).equals(expectedLocale), "Unexpected Java format locale");
        if (usLocale) {
            require(Currency.getInstance(Locale.getDefault()).equals(Currency.getInstance("USD")),
                    "US Java locale must resolve USD");
        }

        if (!args[0].equals("environment") && !usLocale) {
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
