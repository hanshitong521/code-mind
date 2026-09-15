package org.springframework.retry.annotation;

public @interface Retryable { int maxAttempts() default 3; String value() default ""; }
