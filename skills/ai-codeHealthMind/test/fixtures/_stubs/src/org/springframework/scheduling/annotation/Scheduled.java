package org.springframework.scheduling.annotation;

public @interface Scheduled { String cron() default ""; long fixedDelay() default -1L; long fixedRate() default -1L; }
