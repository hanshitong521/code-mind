package com.baomidou.mybatisplus.core.mapper;

public interface BaseMapper<T> { T selectById(java.io.Serializable id); java.util.List<T> selectBatchIds(java.util.Collection<? extends java.io.Serializable> ids); java.util.List<T> selectList(Object wrapper); int insert(T entity); int updateById(T entity); int deleteById(java.io.Serializable id); }
