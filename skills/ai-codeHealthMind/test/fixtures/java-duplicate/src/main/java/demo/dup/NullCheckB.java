package demo.dup;

public class NullCheckB {

    public String title(String value) {
        if (value == null) {
            return "unknown";
        }
        return value;
    }
}
