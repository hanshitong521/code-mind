package demo.refl;

import java.lang.reflect.Method;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExporterFactory {

    @Bean
    public Exporter exporter() {
        return new Exporter();
    }

    public String invoke(String className) throws ReflectiveOperationException {
        Class<?> type = Class.forName(className);
        Method method = type.getDeclaredMethod("render");
        Object instance = type.getDeclaredConstructor().newInstance();
        return String.valueOf(method.invoke(instance));
    }
}
