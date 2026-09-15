package demo.err;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

public class OptionalLoader {

    public Optional<String> load(Path path) {
        try {
            return Optional.of(Files.readString(path));
        } catch (IOException ex) {
            return Optional.empty();
        }
    }
}
