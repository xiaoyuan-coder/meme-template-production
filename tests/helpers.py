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
        "promptTemplate": "双臂紧紧抱住画面中央的{{ subject | \"橘白猫\" }}。",
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
                }
            },
            "visualContract": {
                "medium": "温暖手绘插画",
                "styleTraits": ["简洁线条"],
                "composition": ["主体居中"],
                "relations": [
                    "保持拥抱接触",
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
        "canvas": "保持完整正方形场景与当前裁切",
        "markPolicy": "删除右下角作者水印，保留猫旁的装饰星星贴纸",
        "frozenSet": ["保持拥抱动作、中心构图、温暖手绘媒介和原文笑点"],
        "visualFeatures": "温暖手绘插画，简洁线条，柔和暖色光，中央拥抱钩子",
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
        "visualFeatures": {
            "medium": "温暖手绘插画",
            "composition": "主体居中",
            "proportions": "自然半身比例",
            "colorAndLight": "柔和暖色光",
            "surface": "纸面纹理",
            "visualHook": "双臂拥抱猫咪",
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
        "schemaVersion": 2,
        "approvedImageSha256": image_sha,
        "visualMechanism": "中央主体紧抱宠物的温暖手绘场景",
        "templateValue": {
            "whySelected": "拥抱关系明确，替换中央主体后仍有直观情绪价值",
            "templateHook": "把中央被拥抱对象换成用户指定的主体",
            "fixedMechanism": ["双臂从前方紧抱中央主体", "中央近景构图"],
            "backendOnlyFacts": ["身份目标完整重绘并统一为温暖手绘媒介"],
        },
        "componentGraph": [
            {"componentId": "subject_main", "role": "identity_subject", "region": "center"}
        ],
        "identityTopology": [{"identityUnitId": "subject", "instanceIds": ["subject_main"]}],
        "textRegions": [],
        "mediumComposition": {
            "medium": "温暖手绘插画",
            "styleTraits": ["简洁线条"],
            "composition": ["主体居中"],
            "colorAndLight": ["柔和暖色光"],
        },
        "spatialRelations": [{"type": "hug_contact", "members": ["subject_main"]}],
        "containers": [],
        "fixedStructure": ["centered-hug", "warm-handdrawn-medium"],
        "editableCandidates": [{
            "slotId": "subject", "componentId": "subject_main", "selected": True,
            "selectionReason": "identity_control", "exclusionReason": None,
        }],
        "counts": {
            "identityCount": 1,
            "visualInstanceCount": 1,
            "uploadAssetCount": 1,
            "inputControlCount": 1,
        },
        "fieldEvidence": {field: [f"approved image evidence for {field}"] for field in evidence_fields},
        "titleEvidence": {
            "templateGrounded": True,
            "usageMotivation": True,
            "spokenNaturalness": True,
            "slotPortability": True,
            "evidence": "标题只使用拥抱关系，替换主体后仍成立",
        },
        "tagEvidence": {
            tag: {
                "visualEvidence": f"图中可见{tag}特征",
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
                "visuallyVisible": True,
                "modelControllable": True,
                "mechanismPreserved": True,
                "selectionReason": "identity_control",
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
                "visualEvidence": "中央主体清晰可寻址且替换后保留拥抱机制",
            }
        },
        "promptCoverage": {
            "allEditableContentCovered": True,
            "slotIds": ["subject"],
            "freeEditableRegionIds": [],
        },
        "singleSlotExhaustion": {
            "selectedSlotIds": ["subject"],
            "axes": {
                axis: {
                    "candidateSlotIds": ["subject"] if axis == "subject" else [],
                    "evidence": f"approved image reviewed for {axis}",
                }
                for axis in (
                    "subject", "text", "object", "clothing", "color", "prop", "scene",
                    "nested_content",
                )
            },
        },
        "translationEquivalences": [],
        "semanticModel": {
            "promptTemplate": draft["promptTemplate"],
            "runtimeSemantics": draft["runtimeSemantics"],
            "componentCoverage": {
                "subject_main": {
                    "targetIds": ["subject_main"],
                    "visualContractFields": ["medium", "styleTraits", "composition", "relations", "colorAndLight"],
                }
            },
            "dynamicFactSources": {"subject": "inputSchema.slots.subject"},
            "completeRedrawByTarget": {"subject_main": True},
            "sourceIsolationByInput": {"subject": True},
        },
        "selfReview": {
            "status": "PASS",
            "reviewedDraftSha256": draft_sha,
            "checks": {
                check: True for check in (
                    "templateValueFocused", "slotScopeMinimal", "imageModesJustified",
                    "groupPolicyJustified", "textRoutingComplete", "titlePortable",
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
