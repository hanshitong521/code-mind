package org.springframework.context.event;

public @interface EventListener { String condition() default ""; }
