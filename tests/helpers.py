from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_formal_draft(key: str = "hug-your-pet") -> dict:
    return {
        "key": key,
        "status": "DRAFT",
        "title": "紧紧抱住画面主角",
        "description": "替换中央主角",
        "imageSize": "1024x1024",
        "imageN": 1,
        "kind": "PROMPT",
        "promptTemplate": "画面中央是{{ subject | \"橘白猫\" }}，背景为{{ background | \"米白纯色背景\" }}。",
        "inputSchema": {
            "version": 2,
            "slots": [{
                "id": "subject",
                "label": "主体",
                "required": False,
                "text": {
                    "allowCustom": True,
                    "placeholder": "输入中央主体，或上传1张清晰主体图",
                    "suggestions": ["三花猫", "银渐层猫", "黑白奶牛猫"],
                    "defaultValue": "橘白猫",
                    "presentation": "suggestions",
                },
                "image": {
                    "promptValue": "图片中的中央主体",
                    "hint": "上传单个人物或宠物",
                    "maxCount": 1,
                    "minWidth": 256,
                    "minHeight": 256,
                    "private": True,
                    "sourceOptions": ["upload", "recent_upload", "asset_library"],
                },
                "resolutionStrategy": "image_over_text",
            }, {
                "id": "background",
                "label": "背景",
                "required": False,
                "text": {
                    "allowCustom": True,
                    "placeholder": "选择或输入背景",
                    "suggestions": ["浅灰纯色背景", "暖黄渐变背景", "蓝色纸纹背景"],
                    "defaultValue": "米白纯色背景",
                    "presentation": "suggestions",
                },
            }],
        },
        "preprocessSteps": [],
        "runtimeSemantics": {
            "version": 2,
            "targetInstances": [{
                "id": "subject_main",
                "kind": "identity_subject",
                "role": "画面中心的拥抱主体",
                "region": "画面中心",
            }, {
                "id": "background_canvas",
                "kind": "content_element",
                "role": "画布背景",
                "region": "前景主角后方的完整画布",
            }],
            "inputBindings": {
                "subject": {
                    "operation": "replace_identity",
                    "targetIds": ["subject_main"],
                    "bindingPolicy": "one_to_one",
                    "renderingMode": "illustration_redraw",
                    "allowedSourceGrouping": ["single_subject"],
                    "groupToSinglePolicy": "reject",
                    "clothingOwnership": "source",
                },
                "background": {
                    "operation": "replace_content",
                    "targetIds": ["background_canvas"],
                    "distributionPolicy": "replace_as_unit",
                },
            },
            "visualContract": {
                "medium": "温暖手绘插画",
                "styleTraits": ["简洁线条"],
                "composition": ["主角居中，背景铺满完整画布"],
                "relations": [
                    "保持拥抱接触",
                    "背景位于主角后方且不遮挡主要轮廓",
                    "身份目标完整重绘并统一为温暖手绘媒介",
                ],
                "colorAndLight": ["柔和暖色光"],
            },
        },
        "metadata": {"tags": ["动物", "拥抱", "手绘", "温暖", "互动"]},
    }


SOURCE_INPUT_BYTES = b"\x89PNG\r\n\x1a\n" + b"source-image-byte-payload"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"approved-pixel-payload"
SOURCE_IMAGE = {
    "uri": "fixture://source.jpg",
    "sha256": hashlib.sha256(SOURCE_INPUT_BYTES).hexdigest(),
    "width": 1024,
    "height": 1024,
    "mime": "image/jpeg",
}


def valid_strategy(producer_module, *, item_id: str = "item-a", revision: int = 1) -> dict:
    prompt_sections = {
        "task": "基于参考图完成整图换图，输出独立模板图",
        "target": "将中央的来源猫替换为一只不同的橘白猫",
        "dependencyClosure": ["同步重绘全身、毛色、项圈和地面影子"],
        "identityGroups": ["单猫身份组一对一替换"],
        "featureAuthority": ["新猫接管身体身份与毛色；影子只随新轮廓重新贴合"],
        "canvas": "保持完整正方形场景与当前裁切",
        "markPolicy": "删除右下角作者水印，保留猫旁的装饰星星贴纸",
        "frozenSet": ["保持拥抱动作、中心构图、温暖手绘媒介和原文笑点"],
        "visualFeatures": "温暖手绘插画，简洁线条，柔和暖色光，中央拥抱钩子；未观察到有价值的刻意缺陷",
        "residualCleanup": "清除旧猫的脸、身体、毛色、项圈、影子和水印残留",
        "spatialRelations": "保持双臂拥抱接触、前后遮挡和四肢解剖",
        "output": "一张 1024x1024 PNG，完整画布，不增加额外文字",
    }
    return {
        "itemId": item_id,
        "revision": revision,
        "ruleVersion": "0.2.0",
        "sourceImageSha256": hashlib.sha256(SOURCE_INPUT_BYTES).hexdigest(),
        "inputImage": {
            "uri": "fixture://source.png",
            "sha256": hashlib.sha256(SOURCE_INPUT_BYTES).hexdigest(),
        },
        "sourcePreview": "artifact://item-a/source-preview.jpg",
        "replacementTarget": "center-cat",
        "replacementValue": "orange-white-cat",
        "sourceCategory": "cat",
        "selectedCategory": "cat",
        "sourceIdentityFingerprint": "source-cat",
        "selectedIdentityFingerprint": "orange-white-cat",
        "identityResearch": {
            "required": False,
            "conclusion": "通用猫咪，无特定 IP 识别需求",
            "confidence": 1,
            "evidenceRefs": [],
            "alternatives": [],
        },
        "sourceIdentityUnitIds": ["cat-a"],
        "identityBindingGroups": [{
            "groupId": "identity-group-a",
            "kind": "identity",
            "relationship": "single_subject",
            "sourceMemberIds": ["cat-a"],
            "targetMemberIds": ["new-cat-a"],
            "requiredComponentIds": ["cat-body", "cat-shadow"],
        }],
        "subjectContinuityEvidence": [{
            "sourceMemberId": "cat-a",
            "targetMemberId": "new-cat-a",
            "source": {
                "roleFunction": "被拥抱的中心宠物", "ageStage": "成年",
                "genderPresentation": "未指定", "count": 1, "category": "cat",
            },
            "target": {
                "roleFunction": "被拥抱的中心宠物", "ageStage": "成年",
                "genderPresentation": "未指定", "count": 1, "category": "cat",
            },
            "evidence": "两者均为单只成年猫并承担相同的拥抱机制角色",
        }],
        "assetUnitIds": ["cat-asset-a"],
        "assetBindingGroups": [{
            "groupId": "asset-a", "kind": "asset", "memberIds": ["cat-asset-a"],
            "requiredComponentIds": ["cat-body", "cat-shadow"],
        }],
        "dependencyClosure": [
            {"componentId": "cat-body", "type": "full_body"},
            {"componentId": "cat-shadow", "type": "shadow"},
        ],
        "featureAuthority": [
            {
                "componentId": "cat-body",
                "authority": "target_identity",
                "instruction": "使用新猫的脸、身体、毛色和项圈身份特征",
                "evidence": "完整猫主体承担本次身份替换",
            },
            {
                "componentId": "cat-shadow",
                "authority": "derived_consistency",
                "instruction": "按新猫轮廓重绘接触影子",
                "evidence": "影子只负责地面接触与光照连续",
            },
        ],
        "textActions": [{
            "regionId": "joke-text", "role": "joke", "action": "preserve", "exactText": "抱紧一点"
        }],
        "markActions": [
            {"regionId": "watermark", "type": "author_watermark", "action": "remove"},
            {"regionId": "sticker", "type": "decorative_sticker", "action": "preserve"},
        ],
        "operations": [{
            "id": "replace-cat",
            "type": "identity_replace",
            "targetRegion": "center",
            "targetComponentIds": ["cat-body", "cat-shadow"],
            "stableAnchors": ["hugging-arms"],
            "clearOldContent": True,
            "relations": ["hug-contact", "front-occlusion"],
        }],
        "targetCanvas": {
            "route": "full_scene", "targetRegion": "full-canvas", "excludedRegions": []
        },
        "frozenSet": ["hugging-action", "center-composition", "joke-text"],
        "mechanismAnalysis": {
            "whyInteresting": "人把猫紧紧抱在中央形成直接而温暖的互动",
            "observableHookFeatures": ["双臂环抱", "猫位于画面中心", "身体与手臂有明确接触"],
            "templateCriticalFeatures": ["拥抱动作", "中心构图", "温暖手绘媒介"],
            "evidence": "移除拥抱接触或中心关系后模板玩法不再成立",
        },
        "visualFeatures": {
            "medium": "温暖手绘插画",
            "composition": "主体居中",
            "proportions": "自然半身比例",
            "colorAndLight": "柔和暖色光",
            "surface": "纸面纹理",
            "visualHook": "双臂拥抱猫咪",
            "intentionalImperfections": "未观察到有价值的刻意缺陷",
        },
        "spatialRelations": ["hug-contact", "front-occlusion"],
        "risks": [{"code": "CONTACT_COMPLEX", "summary": "需要复核拥抱接触"}],
        "promptSections": prompt_sections,
        "prompt": producer_module.compile_replacement_prompt(prompt_sections),
        "image_size": "1024x1024",
    }


def valid_approved_analysis(image_sha: str) -> dict:
    draft = valid_formal_draft()
    evidence_fields = [
        "key", "title", "description", "tags", "imageSize", "slots", "suggestions",
        "defaults", "text", "subjectsAndIdentityBindings", "promptTemplate",
        "visualContract", "inputBindings", "clothingOwnership", "cover", "referenceImage",
    ]
    tags = ["动物", "拥抱", "手绘", "温暖", "互动"]
    draft_sha = hashlib.sha256(json.dumps(
        draft, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return {
        "schemaVersion": 6,
        "approvedImageSha256": image_sha,
        "visualMechanism": "中央主体紧抱宠物的温暖手绘场景",
        "templateValue": {
            "whySelected": "拥抱关系明确，替换中央主体后仍有直观情绪价值",
            "templateHook": "把中央被拥抱对象换成用户指定的主体",
            "fixedMechanism": ["双臂从前方紧抱中央主体", "中央近景构图"],
            "backendOnlyFacts": ["身份目标完整重绘并统一为温暖手绘媒介"],
        },
        "playDecisionModel": {
            "funProposition": "用力拥抱与宠物被挤在中央的反应形成温暖又有趣的互动",
            "userRecreationWish": "用户想把自己的宠物放进被紧紧抱住的场景",
            "coreUserDecisions": [{
                "decisionId": "choose_hugged_subject",
                "description": "选择中央被拥抱的宠物身份",
                "slotId": "subject",
                "evidence": "中央宠物是用户个性化结果的焦点",
            }, {
                "decisionId": "choose_background",
                "description": "选择画布背景",
                "slotId": "background",
                "evidence": "本模板背景边界清楚，替换后不破坏拥抱机制",
            }],
        },
        "componentGraph": [
            {"componentId": "subject_main", "role": "identity_subject", "region": "center"},
            {"componentId": "background_canvas", "role": "background", "region": "full_canvas"},
        ],
        "identityTopology": [{"identityUnitId": "subject", "instanceIds": ["subject_main"]}],
        "textRegions": [],
        "mediumComposition": {
            "medium": "温暖手绘插画",
            "styleTraits": ["简洁线条"],
            "composition": ["主角居中，背景铺满完整画布"],
            "colorAndLight": ["柔和暖色光"],
        },
        "spatialRelations": [{"type": "hug_contact", "members": ["subject_main"]}],
        "containers": [],
        "fixedStructure": ["centered-hug", "warm-handdrawn-medium"],
        "editableCandidates": [{
            "slotId": "subject", "componentId": "subject_main", "selected": True,
            "selectionReason": "identity_control", "exclusionReason": None,
        }, {
            "slotId": "background", "componentId": "background_canvas", "selected": True,
            "selectionReason": "template_hook", "exclusionReason": None,
        }],
        "slotCoverageReview": {
            "selectedSlotIds": ["subject", "background"],
            "axes": {
                axis: {
                    "candidateComponentIds": (
                        ["subject_main"] if axis == "subject"
                        else ["background_canvas"] if axis == "scene"
                        else []
                    ),
                    "selectedSlotIds": (
                        ["subject"] if axis == "subject"
                        else ["background"] if axis == "scene"
                        else []
                    ),
                    "evidence": f"approved image reviewed for {axis}",
                }
                for axis in (
                    "subject", "text", "object", "clothing", "color", "prop", "scene",
                    "nested_content",
                )
            },
        },
        "counts": {
            "identityCount": 1,
            "visualInstanceCount": 1,
            "uploadAssetCount": 1,
            "inputControlCount": 2,
        },
        "fieldEvidence": {field: [f"approved image evidence for {field}"] for field in evidence_fields},
        "titleEvidence": {
            "templateGrounded": True,
            "usageMotivation": True,
            "spokenNaturalness": True,
            "slotPortability": True,
            "userAppeal": True,
            "discoveryValue": True,
            "evidence": "标题只使用拥抱关系，替换主体后仍成立",
        },
        "descriptionEvidence": {
            "userFacing": True,
            "complementsTitle": True,
            "spokenNaturalness": True,
            "slotPortability": True,
            "evidence": "描述用日常语言补充模板用法，且不锁定开放值",
        },
        "tagEvidence": {
            tag: {
                "visualEvidence": f"图中可见{tag}特征",
                "searchIntent": f"用户搜索{tag}相关模板",
                "category": {
                    "动物": "subject", "拥抱": "mechanism", "手绘": "medium",
                    "温暖": "emotion", "互动": "relation",
                }[tag],
            }
            for tag in tags
        },
        "slotEvidence": {
            "subject": {
                "userMotivation": True,
                "independentUserChoice": True,
                "meaningfulVariation": True,
                "visuallyVisible": True,
                "modelControllable": True,
                "mechanismPreserved": True,
                "selectionReason": "identity_control",
                "decisionId": "choose_hugged_subject",
                "defaultValue": "橘白猫",
                "semanticAxis": "中央被拥抱主体的身份",
                "granularity": "单一主体类型",
                "defaultLanguageReview": {
                    "natural": True,
                    "concise": True,
                    "modifierMinimal": True,
                },
                "identityRecognition": {
                    "status": "unrecognized",
                    "canonicalName": None,
                    "evidence": "当前图只支持识别为橘白猫，不支持具体命名身份",
                },
                "inputModeDecision": {
                    "modes": ["text", "image"],
                    "reason": "identity_subject",
                    "evidence": "中央主体清晰可寻址，用户会自然提供单主体图片",
                },
                "suggestionChecks": [
                    {"value": value, "sameAxis": True, "sameGranularity": True,
                     "mechanismCompatible": True}
                    for value in ("三花猫", "银渐层猫", "黑白奶牛猫")
                ],
                "openVisualFacts": [
                    "橘白猫", "三花猫", "银渐层猫", "黑白奶牛猫",
                ],
                "bindingKind": "one_to_one",
                "inheritFromUpload": ["可辨认身份特征", "服装", "表情"],
                "keepFromTemplate": ["拥抱动作"],
                "sourceIsolation": True,
                "clothingOwnership": "source",
                "featureAuthority": {
                    "identity": {"authority": "source", "basis": "identity_fidelity",
                                 "evidence": "用户图决定主体身份"},
                    "body": {"authority": "source", "basis": "identity_fidelity",
                             "evidence": "体型属于身份辨识特征"},
                    "ageStage": {"authority": "source", "basis": "identity_fidelity",
                                 "evidence": "当前模板没有年龄转换玩法"},
                    "hair": {"authority": "source", "basis": "identity_fidelity",
                             "evidence": "发型属于身份辨识特征"},
                    "clothing": {"authority": "source", "basis": "appearance_continuity",
                                 "evidence": "普通服装不承担拥抱玩法"},
                    "accessories": {"authority": "source", "basis": "appearance_continuity",
                                    "evidence": "普通配饰跟随身份外观"},
                    "expression": {"authority": "template", "basis": "core_mechanism",
                                   "evidence": "温暖表情承担情绪钩子"},
                    "pose": {"authority": "template", "basis": "composition_dependency",
                             "evidence": "中心姿势决定构图"},
                    "action": {"authority": "template", "basis": "core_mechanism",
                               "evidence": "拥抱动作是模板机制"},
                },
                "visualEvidence": "中央主体清晰可寻址且替换后保留拥抱机制",
            },
            "background": {
                "userMotivation": True,
                "independentUserChoice": True,
                "meaningfulVariation": True,
                "visuallyVisible": True,
                "modelControllable": True,
                "mechanismPreserved": True,
                "selectionReason": "template_hook",
                "decisionId": "choose_background",
                "defaultValue": "米白纯色背景",
                "semanticAxis": "画布背景",
                "granularity": "单一背景设定",
                "defaultLanguageReview": {
                    "natural": True,
                    "concise": True,
                    "modifierMinimal": True,
                },
                "inputModeDecision": {
                    "modes": ["text"],
                    "reason": "text_only",
                    "evidence": "背景可用文字稳定指定，无需精确素材映射",
                },
                "suggestionChecks": [
                    {"value": value, "sameAxis": True, "sameGranularity": True,
                     "mechanismCompatible": True}
                    for value in ("浅灰纯色背景", "暖黄渐变背景", "蓝色纸纹背景")
                ],
                "openVisualFacts": [
                    "米白纯色背景", "浅灰纯色背景", "暖黄渐变背景", "蓝色纸纹背景",
                ],
                "bindingKind": "replace_content",
                "visualEvidence": "完整画布背景清晰可见并可独立替换",
            },
        },
        "promptCoverage": {
            "allEditableContentCovered": True,
            "slotIds": ["subject", "background"],
            "freeEditableRegionIds": [],
            "editableFactIds": ["subject_identity", "background_appearance"],
            "visualElementRoutes": [{
                "componentId": "subject_main",
                "route": "slot",
                "slotId": "subject",
                "factIds": ["subject_identity"],
                "evidence": "中央主体由 subject 槽位控制",
            }, {
                "componentId": "background_canvas",
                "route": "slot",
                "slotId": "background",
                "factIds": ["background_appearance"],
                "evidence": "完整画布背景由 background 槽位控制",
            }],
        },
        "editableFactRouting": [{
            "factId": "subject_identity",
            "axis": "identity",
            "owner": "slot",
            "slotId": "subject",
            "promptTerms": ["橘白猫"],
            "forbiddenRuntimeTerms": ["橘白猫"],
            "requiredTargetIds": ["subject_main"],
            "evidence": "主体身份在 Prompt Template 中由 subject 槽位编辑",
        }, {
            "factId": "background_appearance",
            "axis": "background",
            "owner": "slot",
            "slotId": "background",
            "promptTerms": ["米白纯色背景"],
            "forbiddenRuntimeTerms": ["米白纯色背景"],
            "requiredTargetIds": ["background_canvas"],
            "evidence": "背景外观在 Prompt Template 中由 background 槽位编辑",
        }],
        "translationEquivalences": [],
        "semanticModel": {
            "promptTemplate": draft["promptTemplate"],
            "runtimeSemantics": draft["runtimeSemantics"],
            "componentCoverage": {
                "subject_main": {
                    "targetIds": ["subject_main"],
                    "visualContractFields": ["medium", "styleTraits", "composition", "relations", "colorAndLight"],
                },
                "background_canvas": {
                    "targetIds": ["background_canvas"],
                    "visualContractFields": ["composition", "relations", "colorAndLight"],
                }
            },
            "dynamicFactSources": {
                "subject": "inputSchema.slots.subject",
                "background": "inputSchema.slots.background",
            },
            "completeRedrawByTarget": {"subject_main": True},
            "sourceIsolationByInput": {"subject": True},
        },
        "selfReview": {
            "status": "PASS",
            "reviewedDraftSha256": draft_sha,
            "checks": {
                check: {"passed": True, "evidence": [f"fixture:{check}"]} for check in (
                    "templateValueFocused", "playHypothesisGrounded", "slotRecallComplete",
                    "slotPrecisionComplete", "semanticUnitsCoherent", "slotScopeMinimal", "imageModesJustified",
                    "groupPolicyJustified", "featureAuthorityComplete", "textRoutingComplete",
                    "textEditLayersComplete", "titlePortable",
                    "copyUserFacingAndSearchable",
                    "promptUserFacing", "placeholdersExact",
                    "suggestionsSubstituteNaturally", "tagsValid",
                    "defaultsNaturalAndIdentitySpecific", "visualContractRespectsInputs",
                )
            },
            "issuesFound": [],
            "revisionsApplied": [],
        },
        "warnings": [],
    }
