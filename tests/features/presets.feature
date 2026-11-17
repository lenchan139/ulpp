@核心
Feature: 内置胶纸预设
  Scenario: 45 一版是 5×9
    When 选择预设 "45"
    Then 列数是 5
    And 行数是 9
    And 份数是 45

  Scenario: 未知预设被拒绝
    When 选择预设 "不存在"
    Then 报 KeyError
