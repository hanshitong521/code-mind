package org.springframework.cloud.openfeign;

public @interface FeignClient { String name() default ""; String url() default ""; }
