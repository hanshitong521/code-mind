package demo.refl;

import java.util.ServiceLoader;
import demo.refl.spi.Plugin;

public class PluginBootstrap {

    public int count() {
        int total = 0;
        for (Plugin plugin : ServiceLoader.load(Plugin.class)) {
            total++;
        }
        return total;
    }
}
