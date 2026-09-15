package org.springframework.transaction.annotation;

public @interface Transactional { String value() default ""; boolean readOnly() default false; }
