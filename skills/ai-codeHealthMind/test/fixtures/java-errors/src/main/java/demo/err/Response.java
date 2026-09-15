package demo.err;

public class Response<T> {

    private final T data;

    private Response(T data) {
        this.data = data;
    }

    public static <T> Response<T> success(T data) {
        return new Response<>(data);
    }

    public static <T> Response<T> failure(String message) {
        return new Response<>(null);
    }

    public T getData() {
        return data;
    }
}
