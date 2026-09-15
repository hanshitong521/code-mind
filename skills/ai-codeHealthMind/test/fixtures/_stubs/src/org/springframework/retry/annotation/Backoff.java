package org.springframework.retry.annotation;

public @interface Backoff { long delay() default 0L; }
