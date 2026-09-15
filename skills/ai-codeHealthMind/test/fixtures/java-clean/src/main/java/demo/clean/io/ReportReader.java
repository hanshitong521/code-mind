package demo.clean.io;

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class ReportReader {

    public List<String> readLines(String path) throws IOException {
        List<String> lines = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(new FileInputStream(path), StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            while (line != null) {
                if (!line.isBlank()) {
                    lines.add(line.trim());
                }
                line = reader.readLine();
            }
        }
        return lines;
    }
}
