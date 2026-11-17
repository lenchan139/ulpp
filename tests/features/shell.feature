@tk
Feature: v2 外壳导航
  Scenario: 下一步换屏并落盘
    Given 一个 v2 外壳
    When 点下一步
    Then 外壳当前站是 "orient"
    And 进度已落盘

  Scenario: 未知语言回退到中文
    Given 一个 v2 外壳 语言 xx
    Then 外壳语言是 "zh_CN"
