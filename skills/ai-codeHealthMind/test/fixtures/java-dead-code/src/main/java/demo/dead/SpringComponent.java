package demo.dead;

import org.springframework.stereotype.Component;

@Component
public class SpringComponent {

    public int scale(int value) {
        return multiply(value);
    }

    private int multiply(int value) {
        return value * 3;
    }
}
