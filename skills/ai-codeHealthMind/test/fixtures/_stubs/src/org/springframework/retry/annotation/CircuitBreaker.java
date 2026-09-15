package org.springframework.retry.annotation;

public @interface CircuitBreaker { int maxAttempts() default 3; }
