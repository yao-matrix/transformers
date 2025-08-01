# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Testing suite for the PyTorch PaliGemma model."""

import copy
import unittest

import pytest
from parameterized import parameterized

from transformers import (
    PaliGemmaConfig,
    PaliGemmaForConditionalGeneration,
    is_torch_available,
)
from transformers.testing_utils import (
    is_flaky,
    require_torch,
    torch_device,
)

from ...generation.test_utils import GenerationTesterMixin
from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin, floats_tensor, ids_tensor


if is_torch_available():
    import torch


class PaliGemma2VisionText2TextModelTester:
    def __init__(
        self,
        parent,
        ignore_index=-100,
        image_token_index=0,
        projector_hidden_act="gelu",
        seq_length=25,
        vision_feature_select_strategy="default",
        vision_feature_layer=-1,
        projection_dim=32,
        text_config={
            "model_type": "gemma2",
            "seq_length": 128,
            "is_training": True,
            # "use_input_mask": True,
            "use_token_type_ids": False,
            "use_labels": True,
            "vocab_size": 99,
            "hidden_size": 32,
            "num_hidden_layers": 2,
            "num_attention_heads": 4,
            "num_key_value_heads": 1,
            "head_dim": 8,
            "intermediate_size": 37,
            "hidden_activation": "gelu_pytorch_tanh",
            "hidden_dropout_prob": 0.1,
            "attention_probs_dropout_prob": 0.1,
            "max_position_embeddings": 512,
            "type_vocab_size": 16,
            "type_sequence_label_size": 2,
            "initializer_range": 0.02,
            "num_labels": 3,
            "num_choices": 4,
            "pad_token_id": 1,
        },
        is_training=True,
        vision_config={
            "use_labels": True,
            "image_size": 20,
            "patch_size": 5,
            "num_image_tokens": 4,
            "num_channels": 3,
            "is_training": True,
            "hidden_size": 32,
            "projection_dim": 32,
            "num_key_value_heads": 1,
            "num_hidden_layers": 2,
            "num_attention_heads": 4,
            "intermediate_size": 37,
            "dropout": 0.1,
            "attention_dropout": 0.1,
            "initializer_range": 0.02,
        },
        use_cache=False,
    ):
        self.parent = parent
        self.ignore_index = ignore_index
        # `image_token_index` is set to 0 to pass "resize_embeddings" test, do not modify
        self.image_token_index = image_token_index
        self.projector_hidden_act = projector_hidden_act
        self.vision_feature_select_strategy = vision_feature_select_strategy
        self.vision_feature_layer = vision_feature_layer
        self.text_config = text_config
        self.vision_config = vision_config
        self.seq_length = seq_length
        self.projection_dim = projection_dim
        self.pad_token_id = text_config["pad_token_id"]

        self.num_hidden_layers = text_config["num_hidden_layers"]
        self.vocab_size = text_config["vocab_size"]
        self.hidden_size = text_config["hidden_size"]
        self.num_attention_heads = text_config["num_attention_heads"]
        self.is_training = is_training

        self.batch_size = 3
        self.num_channels = vision_config["num_channels"]
        self.image_size = vision_config["image_size"]
        self.encoder_seq_length = seq_length
        self.use_cache = use_cache

    def get_config(self):
        return PaliGemmaConfig(
            text_config=self.text_config,
            vision_config=self.vision_config,
            ignore_index=self.ignore_index,
            image_token_index=self.image_token_index,
            projector_hidden_act=self.projector_hidden_act,
            projection_dim=self.projection_dim,
            vision_feature_select_strategy=self.vision_feature_select_strategy,
            vision_feature_layer=self.vision_feature_layer,
        )

    def prepare_config_and_inputs(self):
        pixel_values = floats_tensor(
            [
                self.batch_size,
                self.vision_config["num_channels"],
                self.vision_config["image_size"],
                self.vision_config["image_size"],
            ]
        )
        config = self.get_config()

        return config, pixel_values

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, pixel_values = config_and_inputs
        input_ids = ids_tensor([self.batch_size, self.seq_length], config.text_config.vocab_size - 1) + 1
        attention_mask = input_ids.ne(self.pad_token_id).to(torch_device)

        # set the 16 first tokens to be image, and ensure that no other tokens are image tokens
        # do not change this unless you modified image size or patch size
        input_ids[input_ids == config.image_token_index] = self.pad_token_id
        input_ids[:, :16] = config.image_token_index
        inputs_dict = {
            "pixel_values": pixel_values,
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": input_ids,
            "token_type_ids": torch.zeros_like(input_ids),
        }
        return config, inputs_dict


@require_torch
class PaliGemma2ForConditionalGenerationModelTest(ModelTesterMixin, GenerationTesterMixin, unittest.TestCase):
    """
    Model tester for `PaliGemmaForConditionalGeneration`.
    """

    all_model_classes = (PaliGemmaForConditionalGeneration,) if is_torch_available() else ()
    pipeline_model_mapping = {"image-text-to-text": PaliGemmaForConditionalGeneration}
    fx_compatible = False
    test_pruning = False
    test_torchscript = False
    test_head_masking = False
    _is_composite = True

    def setUp(self):
        self.model_tester = PaliGemma2VisionText2TextModelTester(self)
        self.config_tester = ConfigTester(self, config_class=PaliGemmaConfig, has_text_modality=False)

    # Copied from tests.models.llava.test_modeling_llava.LlavaForConditionalGenerationModelTest.test_mismatching_num_image_tokens
    def test_mismatching_num_image_tokens(self):
        """
        Tests that VLMs through an error with explicit message saying what is wrong
        when number of images doesn't match number of image tokens in the text.
        Also we need to test multi-image cases when one prompr has multiple image tokens.
        """
        config, input_dict = self.model_tester.prepare_config_and_inputs_for_common()
        for model_class in self.all_model_classes:
            model = model_class(config).to(torch_device)
            curr_input_dict = copy.deepcopy(input_dict)  # in=place modifications further
            _ = model(**curr_input_dict)  # successful forward with no modifications

            # remove one image but leave the image token in text
            curr_input_dict["pixel_values"] = curr_input_dict["pixel_values"][-1:, ...]
            with self.assertRaises(ValueError):
                _ = model(**curr_input_dict)

            # simulate multi-image case by concatenating inputs where each has exactly one image/image-token
            input_ids = curr_input_dict["input_ids"][:1]
            pixel_values = curr_input_dict["pixel_values"][:1]
            input_ids = torch.cat([input_ids, input_ids], dim=0)

            # one image and two image tokens raise an error
            with self.assertRaises(ValueError):
                _ = model(input_ids=input_ids, pixel_values=pixel_values)

            # two images and two image tokens don't raise an error
            pixel_values = torch.cat([pixel_values, pixel_values], dim=0)
            _ = model(input_ids=input_ids, pixel_values=pixel_values)

    @unittest.skip(
        reason="This architecture seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing(self):
        pass

    @unittest.skip(
        reason="This architecture seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant(self):
        pass

    @unittest.skip(
        reason="This architecture seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant_false(self):
        pass

    @unittest.skip(reason="Some undefined behavior encountered with test versions of this model. Skip for now.")
    def test_cpu_offload(self):
        pass

    @unittest.skip(reason="Some undefined behavior encountered with test versions of this model. Skip for now.")
    def test_disk_offload_bin(self):
        pass

    @unittest.skip(reason="Some undefined behavior encountered with test versions of this model. Skip for now.")
    def test_disk_offload_safetensors(self):
        pass

    @unittest.skip(reason="Some undefined behavior encountered with test versions of this model. Skip for now.")
    def test_model_parallelism(self):
        pass

    @unittest.skip(
        reason="PaliGemma's SigLip encoder uses the same initialization scheme as the Flax original implementation"
    )
    def test_initialization(self):
        pass

    # TODO extend valid outputs to include this test @Molbap
    @unittest.skip(reason="PaliGemma has currently one output format.")
    def test_model_outputs_equivalence(self):
        pass

    # TODO fix the loss = nan in the testing configuration chosen @Molbap
    @unittest.skip(reason="Edge case giving loss nan values in testing configuration.")
    def test_determinism(self):
        pass

    @unittest.skip(reason="PaliGemma does not use feedforward chunking.")
    def test_feed_forward_chunking(self):
        pass

    @unittest.skip(
        "VLMs need lots of steps to prepare images/mask correctly to get pad-free inputs. Can be tested as part of LLM test"
    )
    def test_flash_attention_2_padding_matches_padding_free_with_position_ids(self):
        pass

    @unittest.skip("Low memory will be removed soon so no need to fix it")
    def test_beam_search_low_memory(self):
        pass

    @parameterized.expand([("random",), ("same",)])
    @pytest.mark.generate
    @unittest.skip("Gemma2 has HybridCache which is not compatible with assisted decoding")
    def test_assisted_decoding_matches_greedy_search(self, assistant_type):
        pass

    @unittest.skip("Gemma2 has HybridCache which is not compatible with assisted decoding")
    def test_prompt_lookup_decoding_matches_greedy_search(self, assistant_type):
        pass

    @pytest.mark.generate
    @unittest.skip("Gemma2 has HybridCache which is not compatible with assisted decoding")
    def test_assisted_decoding_sample(self):
        pass

    @unittest.skip("Gemma2 has HybridCache which is not compatible with dola decoding")
    def test_dola_decoding_sample(self):
        pass

    @unittest.skip("Gemma2 has HybridCache and doesn't support continue from past kv")
    def test_generate_continue_from_past_key_values(self):
        pass

    @unittest.skip("Gemma2 has HybridCache and doesn't support contrastive generation")
    def test_contrastive_generate(self):
        pass

    @unittest.skip("Gemma2 has HybridCache and doesn't support contrastive generation")
    def test_contrastive_generate_dict_outputs_use_cache(self):
        pass

    @unittest.skip("Gemma2 has HybridCache and doesn't support contrastive generation")
    def test_contrastive_generate_low_memory(self):
        pass

    @unittest.skip("Gemma2 has HybridCache and doesn't support StaticCache")
    def test_generate_with_static_cache(self):
        pass

    @pytest.mark.generate
    @is_flaky
    def test_generate_compile_model_forward(self):
        super().test_generate_compile_model_forward()

    @unittest.skip("Paligemma position ids are 1 indexed")
    def test_eager_padding_matches_padding_free_with_position_ids(self):
        pass

    @unittest.skip("Paligemma position ids are 1 indexed")
    def test_sdpa_padding_matches_padding_free_with_position_ids(self):
        pass
