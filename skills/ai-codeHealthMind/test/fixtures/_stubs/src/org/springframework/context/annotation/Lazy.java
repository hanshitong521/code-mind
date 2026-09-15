package org.springframework.context.annotation;

public @interface Lazy { boolean value() default true; }
