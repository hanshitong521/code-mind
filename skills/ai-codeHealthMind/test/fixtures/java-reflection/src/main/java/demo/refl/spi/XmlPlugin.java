package demo.refl.spi;

public class XmlPlugin implements Plugin {

    @Override
    public String id() {
        return "xml";
    }

    @Override
    public String render(String input) {
        return "<value>" + input + "</value>";
    }
}
