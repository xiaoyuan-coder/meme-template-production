from __future__ import annotations

import copy
import unittest

from helpers import load_module


compiler = load_module(
    "json_compiler_editability_badcases",
    "skills/meme-template-json-compiler/scripts/compiler.py",
)


class EditabilityBadcaseTests(unittest.TestCase):
    def test_editability_rejects_forbidden_terms_in_target_role_and_region(self):
        case = {
            "caseId": "stale-target-copy",
            "promptTemplate": (
                '{{ headwear | "红色快餐帽" }}和{{ snack | "一盒薯条" }}'
                '组成双宠快餐海报。'
            ),
            "visualContract": {
                "composition": ["两个圆形头像并排，头饰、零食和主口号组成快餐海报。"],
            },
            "targetInstances": [{
                "id": "headwear_target",
                "role": "戴红帽一起应援的双人头饰",
                "region": "两个头像上方的红帽区域",
            }, {
                "id": "snack_target",
                "role": "左上方的薯条",
                "region": "拱门旁的一盒薯条区域",
            }],
            "inputBindings": {
                "headwear": {"targetIds": ["headwear_target"]},
                "snack": {"targetIds": ["snack_target"]},
            },
            "editableFacts": [{
                "factId": "headwear", "owner": "slot", "slotId": "headwear",
                "promptTerms": ["红色快餐帽"],
                "forbiddenRuntimeTerms": ["红色快餐帽", "红帽"],
                "requiredTargetIds": ["headwear_target"],
            }, {
                "factId": "snack", "owner": "slot", "slotId": "snack",
                "promptTerms": ["一盒薯条"],
                "forbiddenRuntimeTerms": ["一盒薯条", "薯条"],
                "requiredTargetIds": ["snack_target"],
            }],
        }

        report = compiler.evaluate_editability_case(case)
        self.assertFalse(report["passed"])
        self.assertEqual(
            {finding["code"] for finding in report["findings"]},
            {"EDITABLE_FACT_LOCKED_IN_RUNTIME_SEMANTICS"},
        )
        self.assertEqual(
            {finding["term"] for finding in report["findings"]},
            {"红帽", "一盒薯条", "薯条"},
        )
        self.assertTrue(all(
            finding["path"].startswith("targetInstances[")
            for finding in report["findings"]
        ))

    def test_regression_surface_assertions_catch_prompt_and_spatial_drift(self):
        template = {
            "key": "scrapbook-fixture",
            "promptTemplate": "主体坐在左下，使用单色网点，愿望物件散落四周。",
            "inputSchema": {"slots": []},
            "runtimeSemantics": {
                "inputBindings": {},
                "targetInstances": [{
                    "id": "subject_target",
                    "role": "中央主体",
                    "region": "画面中央偏左",
                }],
                "visualContract": {
                    "composition": ["主体位于中央偏右。"],
                    "relations": ["右下心形照片压在前景。"],
                },
            },
            "metadata": {"tags": []},
        }
        suite = {
            "suiteId": "cross-surface-drift",
            "cases": [{
                "caseId": "scrapbook",
                "templateKey": "scrapbook-fixture",
                "expectedSlotIds": [],
                "completeObjectSlots": [],
                "editableFacts": [],
                "tagging": None,
                "surfaceAssertions": [{
                    "path": "promptTemplate",
                    "requiredTerms": ["中央偏左"],
                    "forbiddenTerms": ["左下", "单色网点"],
                }, {
                    "path": "runtimeSemantics",
                    "requiredTerms": ["中央偏左"],
                    "forbiddenTerms": ["中央偏右", "心形照片"],
                }],
            }],
        }

        report = compiler.evaluate_template_regression_suite([template], suite)
        self.assertFalse(report["passed"])
        self.assertEqual(
            {finding["code"] for finding in report["findings"]},
            {"REGRESSION_SURFACE_TERM_MISSING", "REGRESSION_SURFACE_TERM_FORBIDDEN"},
        )

    def test_regression_suite_rejects_missing_case_partial_object_and_tag_drift(self):
        heart = {
            "key": "heart-card-fixture",
            "promptTemplate": (
                '{{ subject | "斑点犬" }}从{{ frame | "蓝色粗边" }}爱心中的云朵'
                '探出上半身，周围散落小花、草莓和星星；'
                '{{ slogan | "SO NO MONDAYS" }}拆成彩色泡泡字。'
            ),
            "inputSchema": {"slots": [{
                "id": "subject", "text": {"defaultValue": "斑点犬", "suggestions": []},
            }, {
                "id": "frame", "text": {
                    "defaultValue": "蓝色粗边",
                    "suggestions": ["粉色粗边", "红色粗边", "彩虹粗边"],
                },
            }, {
                "id": "slogan", "text": {"defaultValue": "SO NO MONDAYS", "suggestions": []},
            }]},
            "runtimeSemantics": {
                "inputBindings": {
                    "subject": {"targetIds": ["subject"]},
                    "frame": {"targetIds": ["frame"]},
                    "slogan": {"targetIds": ["slogan"]},
                },
                "visualContract": {
                    "composition": ["小花、草莓和星星散落四周"],
                    "styleTraits": ["字母有黑线或花形底"],
                },
            },
            "metadata": {
                "tags": ["动物", "文字设计", "爱心卡片", "泡泡字", "宠物拼贴", "复古印刷"],
            },
        }
        suite = {
            "suiteId": "three-editability-badcases",
            "cases": [{
                "caseId": "heart-card",
                "templateKey": "heart-card-fixture",
                "expectedSlotIds": ["subject", "frame", "decorations", "slogan"],
                "completeObjectSlots": [{
                    "slotId": "frame",
                    "objectTerms": ["爱心", "圆框", "星形框"],
                }],
                "editableFacts": [{
                    "factId": "decorations", "owner": "slot", "slotId": "decorations",
                    "promptTerms": ["小花、草莓和星星"],
                    "forbiddenRuntimeTerms": ["小花、草莓和星星"],
                    "requiredTargetIds": ["flowers", "fruit", "stars"],
                }],
                "tagging": {
                    "matchProfile": {
                        "subjects": [{"subjectKey": "pet.dog", "memberCount": 1}],
                        "sourceImageType": "single_identity",
                    },
                    "hiddenTags": ["动物", "文字设计"],
                    "keywords": ["狗", "爱心卡片", "泡泡字", "宠物拼贴", "复古印刷"],
                },
            }, {
                "caseId": "required-second-case",
                "templateKey": "missing-fixture",
                "expectedSlotIds": [],
                "completeObjectSlots": [],
                "editableFacts": [],
                "tagging": None,
            }],
        }

        report = compiler.evaluate_template_regression_suite([heart], suite)
        self.assertFalse(report["passed"])
        codes = {finding["code"] for finding in report["findings"]}
        self.assertEqual(
            codes,
            {
                "REGRESSION_TEMPLATE_MISSING",
                "REGRESSION_SLOT_SET_MISMATCH",
                "REGRESSION_PARTIAL_VISUAL_OBJECT",
                "EDITABLE_FACT_LOCKED_IN_VISUAL_CONTRACT",
                "EDITABLE_DEPENDENCY_TARGET_UNBOUND",
                "REGRESSION_TAG_ASSEMBLY_MISMATCH",
            },
        )

    def test_regression_suite_accepts_complete_object_group_binding_and_tags(self):
        heart = {
            "key": "heart-card-fixture",
            "promptTemplate": (
                '{{ subject | "斑点犬" }}从{{ frame | "蓝色粗边爱心" }}里的白色云朵后'
                '探出上半身，周围散落{{ decorations | "小花、草莓和星星" }}；'
                '{{ slogan | "SO NO MONDAYS" }}拆成彩色泡泡字。'
            ),
            "inputSchema": {"slots": [{
                "id": "subject", "text": {"defaultValue": "斑点犬", "suggestions": []},
            }, {
                "id": "frame", "text": {
                    "defaultValue": "蓝色粗边爱心",
                    "suggestions": ["粉色波浪边爱心", "红色圆框", "彩虹星形框"],
                },
            }, {
                "id": "decorations", "text": {
                    "defaultValue": "小花、草莓和星星", "suggestions": [],
                },
            }, {
                "id": "slogan", "text": {"defaultValue": "SO NO MONDAYS", "suggestions": []},
            }]},
            "runtimeSemantics": {
                "inputBindings": {
                    "subject": {"targetIds": ["subject"]},
                    "frame": {"targetIds": ["frame"]},
                    "decorations": {"targetIds": ["flowers", "fruit", "stars"]},
                    "slogan": {"targetIds": ["slogan"]},
                },
                "visualContract": {
                    "composition": ["协调装饰组散落在主体四周"],
                    "styleTraits": ["保留复古印刷网点"],
                },
            },
            "metadata": {
                "tags": ["动物", "文字设计", "狗", "爱心卡片", "泡泡字", "宠物拼贴", "复古印刷"],
            },
        }
        suite = {
            "suiteId": "heart-editability",
            "cases": [{
                "caseId": "heart-card",
                "templateKey": "heart-card-fixture",
                "expectedSlotIds": ["subject", "frame", "decorations", "slogan"],
                "completeObjectSlots": [{
                    "slotId": "frame", "objectTerms": ["爱心", "圆框", "星形框"],
                }],
                "editableFacts": [{
                    "factId": "decorations", "owner": "slot", "slotId": "decorations",
                    "promptTerms": ["小花、草莓和星星"],
                    "forbiddenRuntimeTerms": ["小花、草莓和星星"],
                    "requiredTargetIds": ["flowers", "fruit", "stars"],
                }],
                "tagging": {
                    "matchProfile": {
                        "subjects": [{"subjectKey": "pet.dog", "memberCount": 1}],
                        "sourceImageType": "single_identity",
                    },
                    "hiddenTags": ["动物", "文字设计"],
                    "keywords": ["狗", "爱心卡片", "泡泡字", "宠物拼贴", "复古印刷"],
                },
            }],
        }

        report = compiler.evaluate_template_regression_suite([heart], suite)
        self.assertTrue(report["passed"], report["findings"])

    def test_candy_bottom_shape_slot_can_change_color_and_shape(self):
        case = {
            "caseId": "candy-bottom-shape-slot",
            "promptTemplate": (
                '{{ subject | "白色短毛猫" }}的正面头像嵌在采用'
                '{{ wrapper | "粉白条纹糖纸" }}的圆形糖果包装中央，'
                '下方露出{{ bottom_shape | "蓝边黄底圆环" }}。'
            ),
            "visualContract": {
                "medium": "宠物摄影头像与实物糖纸合成图标",
                "styleTraits": ["底部图形边缘平滑清楚"],
                "relations": ["底部图形位于包装下层"],
            },
            "inputBindings": {
                "bottom_shape": {
                    "operation": "replace_content",
                    "targetIds": ["bottom_shape_target"],
                }
            },
            "editableFacts": [{
                "factId": "bottom_shape",
                "owner": "slot",
                "slotId": "bottom_shape",
                "promptTerms": ["蓝边黄底圆环"],
                "forbiddenRuntimeTerms": ["蓝边黄底圆环", "黄蓝圆环"],
                "requiredTargetIds": ["bottom_shape_target"],
            }],
        }

        self.assertTrue(compiler.evaluate_editability_case(case)["passed"])

    def test_candy_wrapper_rejects_legacy_ring_color_in_visual_contract(self):
        case = {
            "caseId": "candy-wrapper-color",
            "promptTemplate": "用旧报纸做糖纸，下方露出褐色边黄底圆环。",
            "visualContract": {
                "medium": "宠物摄影与实物糖纸拼贴",
                "composition": ["圆形头像被糖纸包围，下方露出蓝边黄底圆环"],
                "relations": ["黄蓝圆环从包装下方露出"],
            },
            "inputBindings": {},
            "editableFacts": [{
                "factId": "ring_appearance",
                "owner": "prompt",
                "promptTerms": ["褐色边黄底圆环"],
                "forbiddenRuntimeTerms": ["蓝边黄底圆环", "黄蓝圆环"],
                "requiredTargetIds": [],
            }],
        }

        report = compiler.evaluate_editability_case(case)
        self.assertFalse(report["passed"])
        self.assertIn(
            "EDITABLE_FACT_LOCKED_IN_VISUAL_CONTRACT",
            {finding["code"] for finding in report["findings"]},
        )
        self.assertEqual(
            {finding["term"] for finding in report["findings"]},
            {"蓝边黄底圆环", "黄蓝圆环"},
        )

        corrected = copy.deepcopy(case)
        corrected["visualContract"]["composition"] = ["圆形头像被糖纸包围，圆环从包装下方露出"]
        corrected["visualContract"]["relations"] = ["圆环从包装下方露出"]
        self.assertTrue(compiler.evaluate_editability_case(corrected)["passed"])

    def test_snack_replacement_requires_every_dependent_target_in_binding(self):
        case = {
            "caseId": "snack-package-dependency",
            "promptTemplate": "萨摩耶从黄瓜味乐事薯片包装中探出头和四肢。",
            "visualContract": {
                "medium": "干净摄影剪贴与商品包装拼贴",
                "relations": ["顶部食物与包装连续"],
            },
            "inputBindings": {
                "snack": {
                    "operation": "replace_content",
                    "targetIds": ["snack_package"],
                }
            },
            "editableFacts": [{
                "factId": "snack_product",
                "owner": "slot",
                "slotId": "snack",
                "promptTerms": ["黄瓜味乐事薯片"],
                "forbiddenRuntimeTerms": [],
                "requiredTargetIds": ["snack_package", "top_food"],
            }],
        }

        report = compiler.evaluate_editability_case(case)
        self.assertFalse(report["passed"])
        self.assertIn(
            "EDITABLE_DEPENDENCY_TARGET_UNBOUND",
            {finding["code"] for finding in report["findings"]},
        )
        self.assertEqual(len(report["findings"]), 1)

        corrected = copy.deepcopy(case)
        corrected["inputBindings"]["snack"]["targetIds"].append("top_food")
        self.assertTrue(compiler.evaluate_editability_case(corrected)["passed"])

    def test_heart_border_rejects_blue_aliases_after_prompt_changes_to_pink(self):
        case = {
            "caseId": "heart-border-color",
            "promptTemplate": "萨摩耶从粉色边爱心中的云朵探出上半身。",
            "visualContract": {
                "medium": "宠物照片与卡通纸片拼贴",
                "styleTraits": ["爱心蓝色粗边"],
                "composition": ["中央主体从蓝边爱心中的云朵探出上半身"],
                "relations": ["爱心蓝边包围整体"],
            },
            "inputBindings": {},
            "editableFacts": [{
                "factId": "heart_border_color",
                "owner": "prompt",
                "promptTerms": ["粉色边爱心"],
                "forbiddenRuntimeTerms": ["爱心蓝色粗边", "蓝边爱心", "爱心蓝边"],
                "requiredTargetIds": [],
            }],
        }

        report = compiler.evaluate_editability_case(case)
        self.assertFalse(report["passed"])
        locked_terms = {
            finding["term"] for finding in report["findings"]
            if finding["code"] == "EDITABLE_FACT_LOCKED_IN_VISUAL_CONTRACT"
        }
        self.assertEqual(
            locked_terms,
            {"爱心蓝色粗边", "蓝边爱心", "爱心蓝边"},
        )

        corrected = copy.deepcopy(case)
        corrected["visualContract"] = {
            "medium": "宠物照片与卡通纸片拼贴",
            "composition": ["中央主体从爱心中的云朵探出上半身"],
            "relations": ["爱心轮廓包围整体"],
        }
        self.assertTrue(compiler.evaluate_editability_case(corrected)["passed"])

    def test_heart_reference_answer_requires_complete_editable_prompt(self):
        case = {
            "caseId": "heart-complete-editable-prompt",
            "promptTemplate": (
                '{{ subject | "斑点犬" }}从{{ frame | "蓝色粗边爱心" }}中的云朵'
                '探出上半身，周围散落{{ decorations | "小花、草莓和星星" }}；'
                '{{ slogan | "SO NO MONDAYS" }}拆成彩色泡泡字。'
            ),
            "visualContract": {
                "medium": "宠物照片与卡通纸片拼贴",
                "composition": ["主体居中，文字上下环绕"],
            },
            "inputBindings": {
                "subject": {"targetIds": ["subject"]},
                "frame": {"targetIds": ["frame"]},
                "decorations": {"targetIds": ["flowers", "fruit", "stars"]},
                "slogan": {"targetIds": ["slogan"]},
            },
            "editableFacts": [{
                "factId": "subject", "owner": "slot", "slotId": "subject",
                "promptTerms": ["斑点犬"], "forbiddenRuntimeTerms": [],
                "requiredTargetIds": ["subject"],
            }, {
                "factId": "frame", "owner": "slot", "slotId": "frame",
                "promptTerms": ["蓝色粗边爱心"], "forbiddenRuntimeTerms": [],
                "requiredTargetIds": ["frame"],
            }, {
                "factId": "decorations", "owner": "slot", "slotId": "decorations",
                "promptTerms": ["小花、草莓和星星"], "forbiddenRuntimeTerms": [],
                "requiredTargetIds": ["flowers", "fruit", "stars"],
            }, {
                "factId": "slogan", "owner": "slot", "slotId": "slogan",
                "promptTerms": ["SO NO MONDAYS"], "forbiddenRuntimeTerms": [],
                "requiredTargetIds": ["slogan"],
            }, {
                "factId": "inner_pattern", "owner": "prompt",
                "promptTerms": ["浅蓝云朵纹理"], "forbiddenRuntimeTerms": [],
                "requiredTargetIds": [],
            }, {
                "factId": "support_cloud", "owner": "prompt",
                "promptTerms": ["白色云朵"], "forbiddenRuntimeTerms": [],
                "requiredTargetIds": [],
            }, {
                "factId": "subject_outline", "owner": "prompt",
                "promptTerms": ["浅黄色贴纸描边"], "forbiddenRuntimeTerms": [],
                "requiredTargetIds": [],
            }, {
                "factId": "letter_treatment", "owner": "prompt",
                "promptTerms": ["黑色描边和花形、圆形、爱心底形"],
                "forbiddenRuntimeTerms": [], "requiredTargetIds": [],
            }],
        }
        report = compiler.evaluate_editability_case(case)
        self.assertFalse(report["passed"])
        self.assertEqual(
            {
                finding["term"] for finding in report["findings"]
                if finding["code"] == "EDITABLE_FACT_MISSING_FROM_PROMPT"
            },
            {"浅蓝云朵纹理", "白色云朵", "浅黄色贴纸描边", "黑色描边和花形、圆形、爱心底形"},
        )

        corrected = copy.deepcopy(case)
        corrected["promptTemplate"] = (
            '{{ subject | "斑点犬" }}从{{ frame | "蓝色粗边爱心" }}里的白色云朵后'
            '探出上半身，主体带浅黄色贴纸描边，爱心内部铺着浅蓝云朵纹理，'
            '周围散落{{ decorations | "小花、草莓和星星" }}；'
            '{{ slogan | "SO NO MONDAYS" }}使用带黑色描边和花形、圆形、爱心底形的彩色泡泡字。'
        )
        self.assertTrue(compiler.evaluate_editability_case(corrected)["passed"])


if __name__ == "__main__":
    unittest.main()
