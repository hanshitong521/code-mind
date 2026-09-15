package demo.refl.spi;

public class JsonPlugin implements Plugin {

    @Override
    public String id() {
        return "json";
    }

    @Override
    public String render(String input) {
        return "{\"value\":\"" + escape(input) + "\"}";
    }

    private String escape(String raw) {
        return raw.replace("\"", "\\\"");
    }
}
