package demo.dead;

import java.lang.reflect.Method;

public class TaskBootstrap {

    public String boot(String className) throws ReflectiveOperationException {
        Class<?> type = Class.forName(className);
        Method method = type.getDeclaredMethod("invokeTask");
        Object instance = type.getDeclaredConstructor().newInstance();
        return String.valueOf(method.invoke(instance));
    }
}
