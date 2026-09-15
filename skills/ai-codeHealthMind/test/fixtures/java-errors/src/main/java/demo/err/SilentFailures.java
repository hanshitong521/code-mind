package demo.err;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SilentFailures {

    private static final Logger log = LoggerFactory.getLogger(SilentFailures.class);

    public String readConfig(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException ex) {
        }
        return "";
    }

    public String loadTenant(String tenantId) {
        try {
            return Files.readString(Path.of("/etc/tenants", tenantId));
        } catch (IOException ex) {
            return null;
        }
    }
}
