"""AI-driven DITA validation error correction."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from hop_core.dita.ai import GenerationRequest, SupportsGenerate
from hop_core.dita.validator import DitaValidator

logger = logging.getLogger(__name__)


class DitaCorrectionService:
    """Corrects DITA validation errors using an injected AI service.

    ``ai_service`` is any object satisfying :class:`SupportsGenerate` — an
    ``async generate(request)`` method returning an object with ``.content``.
    """

    def __init__(self, ai_service: SupportsGenerate, validator: Optional[DitaValidator] = None):
        """Initialize with AI service and validator."""
        self.ai_service = ai_service
        self.validator = validator or DitaValidator()

    async def correct_validation_errors(
        self,
        content: str,
        max_attempts: int = 3,
        preserve_text: bool = True,
        topic_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Tuple[str, bool, List[str]]:
        """
        Attempt to correct DITA validation errors using AI.

        Args:
            content: DITA content with validation errors
            max_attempts: Maximum correction attempts
            preserve_text: Whether to preserve original text content
            topic_id: ID to use if a stripped topic root must be rebuilt
            title: Title to use if a stripped topic root must be rebuilt

        Returns:
            Tuple of (corrected_content, success, correction_log)
        """
        correction_log = []
        current_content = content
        if topic_id is None or title is None:
            detected_id, detected_title = self._extract_topic_identity(content)
            topic_id = topic_id or detected_id
            title = title or detected_title

        for attempt in range(1, max_attempts + 1):
            # Validate current content (DTD if available, structural otherwise)
            valid, errors = self.validator.validate_with_dtd(current_content)

            if valid:
                correction_log.append(f"Attempt {attempt}: Validation successful")
                return current_content, True, correction_log

            correction_log.append(f"Attempt {attempt}: Found {len(errors) if errors else 0} validation errors")

            # Extract detailed error information
            error_details = self.validator.extract_validation_errors(current_content)

            # Generate correction prompt
            correction_prompt = self._generate_correction_prompt(
                current_content,
                error_details,
                preserve_text
            )

            # Get AI correction
            try:
                corrected_content = await self._get_ai_correction(correction_prompt)

                # The LLM sometimes returns body-level content (one or more
                # <section> elements) without the <topic> wrapper, which yields
                # an invalid <section> root. Deterministically restore a valid
                # topic root before validating.
                corrected_content = self.validator.ensure_topic_root(
                    corrected_content, topic_id=topic_id, title=title
                )

                # Validate the correction
                valid_after, errors_after = self.validator.validate_with_dtd(corrected_content)

                if valid_after:
                    correction_log.append(f"Attempt {attempt}: AI correction successful")
                    return corrected_content, True, correction_log

                # Check if we made progress
                if errors_after and errors and len(errors_after) < len(errors):
                    correction_log.append(f"Attempt {attempt}: Reduced errors from {len(errors)} to {len(errors_after)}")
                    current_content = corrected_content
                else:
                    correction_log.append(f"Attempt {attempt}: No improvement, keeping previous version")

            except Exception as e:
                correction_log.append(f"Attempt {attempt}: AI correction failed - {str(e)}")

        # Final validation attempt with auto-fixes
        correction_log.append("Applying automatic fixes as final attempt")
        final_content = self.validator.auto_fix_common_issues(current_content)
        final_content = self.validator.ensure_topic_root(
            final_content, topic_id=topic_id, title=title
        )
        valid_final, _ = self.validator.validate_with_dtd(final_content)

        return final_content, valid_final, correction_log

    def _generate_correction_prompt(
        self,
        content: str,
        errors: Dict[str, Any],
        preserve_text: bool = True
    ) -> str:
        """Generate prompt for AI to correct validation errors."""

        if preserve_text:
            prompt = """You are a DITA XML validation expert. Fix the validation errors below while STRICTLY preserving all text content.

CRITICAL RULES:
1. DO NOT change any text content - preserve it exactly (including typos, case, punctuation)
2. DO NOT add or remove any text
3. DO NOT reorder sections or content
4. ONLY fix XML/DITA structural issues
5. Make minimal changes needed to fix validation errors

"""
        else:
            prompt = """You are a DITA XML validation expert. Fix the validation errors below.

RULES:
1. Fix all XML/DITA structural issues
2. Ensure valid DITA 1.3 structure
3. Make content well-formed and valid

"""

        prompt += "VALIDATION ERRORS TO FIX:\n"

        # Add general errors
        if errors.get("errors"):
            prompt += "\nGeneral Errors:\n"
            for error in errors["errors"]:
                prompt += f"• {error}\n"

        # Add line-specific errors
        if errors.get("line_errors"):
            prompt += "\nLine-Specific Errors:\n"
            for line_no, line_errors in sorted(errors["line_errors"].items()):
                prompt += f"Line {line_no}:\n"
                for error in line_errors:
                    prompt += f"  • {error}\n"

        prompt += """
COMMON FIXES NEEDED:
• Add missing <title> element after <topic>
• Add missing <body> element after <title>
• Fix invalid ID format (must start with letter, use only letters/numbers/underscore/hyphen)
• Move text content into <p> tags (structural elements like <section> can't have direct text)
• Add <title> to any <section> elements
• Ensure lists (<ul>/<ol>) contain <li> elements
• Escape special characters (&→&amp; <→&lt; >→&gt;)
• Close all opened tags properly

CURRENT DITA CONTENT:
```xml
{}
```

Return ONLY the corrected DITA XML. Do not include any explanation, commentary, or markdown formatting.
""".format(content)

        return prompt

    def _extract_topic_identity(self, content: str) -> Tuple[str, str]:
        """Extract the root id and title from valid DITA content.

        Used so that if a downstream correction step strips the topic wrapper,
        ensure_topic_root can rebuild it with the original id and title rather
        than generic defaults. Falls back to sensible defaults when absent.
        """
        topic_id = "release-notes"
        title = "Release Notes"
        try:
            from lxml import etree
            parser = etree.XMLParser(recover=True, no_network=True, resolve_entities=False)
            doc = etree.fromstring(content.encode("utf-8"), parser)
            if doc is not None:
                if doc.get("id"):
                    topic_id = doc.get("id")
                title_el = doc.find("title")
                if title_el is not None and title_el.text and title_el.text.strip():
                    title = title_el.text.strip()
        except Exception:
            pass
        return topic_id, title

    def _detect_topic_type(self, content: str) -> str:
        """Return the root DITA element name (topic, concept, task, reference, …)."""
        try:
            from lxml import etree
            parser = etree.XMLParser(recover=True, no_network=True, resolve_entities=False)
            doc = etree.fromstring(content.encode("utf-8"), parser)
            tag = doc.tag
            if tag in self.validator.DTD_FILES:
                return tag
        except Exception:
            pass
        # Fallback: scan for the first recognised root open tag
        for t in ("concept", "task", "reference", "topic"):
            if f"<{t}" in content:
                return t
        return "topic"

    async def _get_ai_correction(self, prompt: str) -> str:
        """Get AI correction for DITA content."""

        system_prompt = """You are a DITA XML validation expert. Your role is to fix DITA structural errors while preserving content.
You must return valid DITA XML that conforms to DITA 1.3 standards.
Never add markdown formatting or explanations - return only pure XML."""

        request = GenerationRequest(
            system_prompt=system_prompt,
            user_prompt=prompt,
            max_tokens=4096,
            temperature=0.1  # Low temperature for consistent corrections
        )

        response = await self.ai_service.generate(request)

        # Clean response (remove any markdown formatting if present)
        corrected = response.content.strip()

        # Remove markdown code blocks if present
        if corrected.startswith("```"):
            lines = corrected.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]  # Remove first line
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # Remove last line
            corrected = '\n'.join(lines)

        return corrected

    async def _regenerate_strict(self, original_prompt: str, content: str) -> str:
        """Regenerate the whole document from the original prompt with a strict
        DITA structure template matching the current topic type."""
        # Detect the topic type from the current content so the regeneration
        # prompt uses the correct DOCTYPE and root element.
        topic_type = self._detect_topic_type(content)
        doctype_hint, root_open, body_element, root_close = {
            "concept": (
                '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">',
                '<concept id="valid_id_here">',
                "<conbody>\n    <!-- Your content sections here -->\n  </conbody>",
                "</concept>",
            ),
            "task": (
                '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">',
                '<task id="valid_id_here">',
                "<taskbody>\n    <!-- Your steps here -->\n  </taskbody>",
                "</task>",
            ),
            "reference": (
                '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">',
                '<reference id="valid_id_here">',
                "<refbody>\n    <!-- Your reference sections here -->\n  </refbody>",
                "</reference>",
            ),
        }.get(topic_type, (
            '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">',
            '<topic id="valid_id_here">',
            "<body>\n    <!-- Your content sections here -->\n  </body>",
            "</topic>",
        ))

        enhanced_prompt = original_prompt + f"""

CRITICAL REQUIREMENT: Generate ONLY valid DITA 1.3 XML with this exact structure:
<?xml version="1.0" encoding="UTF-8"?>
{doctype_hint}
{root_open}
  <title>Title Here</title>
  {body_element}
{root_close}

Ensure all content is in valid DITA elements. No markdown, no plain text outside of elements."""

        request = GenerationRequest(
            system_prompt="Generate valid DITA 1.3 XML only. No markdown.",
            user_prompt=enhanced_prompt,
            max_tokens=4096,
            temperature=0.3,
        )
        response = await self.ai_service.generate(request)
        return response.content.strip()

    async def validate_and_correct_with_ai(
        self,
        content: str,
        original_prompt: Optional[str] = None,
        max_iterations: Optional[int] = None,
        max_cycles: Optional[int] = None,
    ) -> Tuple[str, bool, List[str]]:
        """
        Validate DITA content and loop it back through the LLM until it passes.

        This is the main entry point for callers. Invalid DITA is a recoverable
        condition, not a failure: the content is repeatedly fed back to the LLM
        (with the specific validation errors) until validation passes.
        ``max_iterations`` is only a safety cap to prevent an infinite loop — in
        practice validation passes within the first one or two iterations.

        ``max_cycles`` is accepted for backward compatibility and treated as an
        alias for ``max_iterations`` when the latter is not given.

        Returns (content, is_valid, log). ``is_valid`` is False only when the
        safety cap is exhausted without producing valid DITA.
        """
        if max_iterations is None:
            max_iterations = max_cycles if max_cycles is not None else 10
        max_iterations = max(1, max_iterations)

        validation_log = []

        # Capture the original topic id / title up front so that if a correction
        # step strips the <topic> wrapper, we can rebuild it faithfully.
        topic_id, title = self._extract_topic_identity(content)

        # First, try deterministic fixes (no LLM call needed).
        validation_log.append("Applying automatic fixes...")
        content = self.validator.auto_fix_common_issues(content)
        content = self.validator.ensure_topic_root(content, topic_id=topic_id, title=title)

        valid, errors = self.validator.validate_with_dtd(content)
        if valid:
            validation_log.append("Content valid after automatic fixes")
            return content, True, validation_log

        validation_log.append(
            f"Validation failed with {len(errors) if errors else 0} error(s); "
            f"looping through the LLM (max {max_iterations} iterations)"
        )

        best_content = content

        # Loop the invalid content back through the LLM until it validates.
        for iteration in range(1, max_iterations + 1):
            # Escalate to a full strict regeneration for the final iterations,
            # when targeted corrections have repeatedly failed to converge.
            use_regeneration = (
                original_prompt is not None
                and iteration > max(1, max_iterations - 2)
            )

            try:
                if use_regeneration:
                    validation_log.append(
                        f"Iteration {iteration}/{max_iterations}: regenerating with stricter DITA requirements"
                    )
                    corrected = await self._regenerate_strict(original_prompt, content)
                else:
                    error_details = self.validator.extract_validation_errors(content)
                    correction_prompt = self._generate_correction_prompt(
                        content, error_details, preserve_text=True
                    )
                    validation_log.append(
                        f"Iteration {iteration}/{max_iterations}: requesting LLM correction "
                        f"for {len(errors) if errors else 0} error(s)"
                    )
                    corrected = await self._get_ai_correction(correction_prompt)
            except Exception as e:
                validation_log.append(f"Iteration {iteration}: AI call failed - {str(e)}")
                continue

            # Always re-apply the deterministic guarantees (valid root, etc.).
            corrected = self.validator.auto_fix_common_issues(corrected)
            corrected = self.validator.ensure_topic_root(corrected, topic_id=topic_id, title=title)

            valid_after, errors_after = self.validator.validate_with_dtd(corrected)
            if valid_after:
                validation_log.append(f"Iteration {iteration}: validation passed")
                return corrected, True, validation_log

            n_after = len(errors_after) if errors_after else 0
            n_before = len(errors) if errors else 0
            if not errors or n_after <= n_before:
                # Progress (or first measurement) — carry the new content forward.
                validation_log.append(f"Iteration {iteration}: still invalid ({n_after} error(s)), retrying")
                content = corrected
                errors = errors_after
                best_content = corrected
            else:
                # Regression — keep the previous, better content for the next try.
                validation_log.append(
                    f"Iteration {iteration}: more errors ({n_after} > {n_before}), "
                    "discarding and retrying from previous version"
                )

        validation_log.append(
            f"Unable to produce valid DITA after {max_iterations} iterations (safety cap reached)"
        )
        return best_content, False, validation_log
