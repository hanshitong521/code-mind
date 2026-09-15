package demo.clean.plugin;

import java.lang.reflect.Method;

public class PluginLoader {

    public String load(String className) throws ReflectiveOperationException {
        Class<?> type = Class.forName(className);
        Method method = type.getDeclaredMethod("export");
        Object instance = type.getDeclaredConstructor().newInstance();
        return String.valueOf(method.invoke(instance));
    }
}
