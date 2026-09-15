package demo.conc;

public class LazyConfig {

    private Config instance;

    public Config get() {
        if (instance == null) {
            synchronized (LazyConfig.class) {
                if (instance == null) {
                    instance = new Config();
                }
            }
        }
        return instance;
    }
}
