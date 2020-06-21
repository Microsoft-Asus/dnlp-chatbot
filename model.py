import tensorflow as tf
import tensorflow.keras.layers as layers


class ChatbotModel:
    """Seq2Seq model using GRU cells.
    
    Format for hyperparameters:
    hparams = {
        'embedding_size': x,
        'units': x,
        'num_layers': x,
        'keep_prob': x,
        'learn_rate': x
    }
    
    Format for vocabulary:
    vocab_int = {
        '<PAD>': 0,
        '<SOS>': 1,
        '<EOS>': 2,
        '<EX>': 3,
        ...
    }
    
    References:
    Tensorflow 2 tutorial: "Neural machine translation with attention"
    SuperDataScience course: "Deep Learning and NLP A-Z: How to Create a Chatbot"
    Lilian Weng's blog: "Attention? Attention!"
    """

    def __init__(self, hparams, vocab_int, filename):
        super(ChatbotModel, self).__init__()
        self.hparams = hparams
        self.encoder = Encoder(len(vocab_int),
                               hparams['embedding_size'],
                               hparams['units'],
                               hparams['num_layers'],
                               dropout=hparams['keep_prob'])
        self.decoder = Decoder(len(vocab_int),
                               hparams['embedding_size'],
                               hparams['units'],
                               hparams['num_layers'],
                               dropout=hparams['keep_prob'])
        self.optimizer = tf.keras.optimizers.Adam(learning_rate=hparams['learn_rate'])
        self.vocab_int = vocab_int
        self.filename = filename
        self.loss_obj = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True,
                                                                      reduction='none')
        self.checkpoint = tf.train.Checkpoint(encoder=self.encoder,
                                              decoder=self.decoder,
                                              optimizer=self.optimizer)


    # def train(self, inputs, targets, epochs, batch_size):
    #     assert len(inputs) == len(targets), 'len(inputs) does not equal len(targets)'
    #     num_batches = len(inputs)
    #     for epoch in range(epochs):
    #         start = time.time()
    #         hidden_state = tf.zeros((batch_size, self.encoder.units))
    #         total_loss = 0


    def train_batch(self, batch_inputs, batch_targets):
        """ Used for mini-batch training.
        batch_inp and batch_targ should be zero-padded.
        """
        assert len(batch_inputs) == len(batch_targets), 'len(batch_inp) does not equal len(batch_targ)'
        batch_size = batch_inputs.shape[0]
        loss = 0
        with tf.GradientTape() as tape:
            init_state = tf.zeros((batch_size, self.encoder.units))
            enc_outputs, hidden_state = self.encoder(batch_inputs, init_state)
            dec_inputs = tf.expand_dims([self.vocab_int['<SOS>']] * batch_size, 1)
            
            # teacher forcing: feeding the target as the next input
            for t in range(1, batch_targets.shape[1]):
                predict_words, _, _ = self.decoder(dec_inputs, hidden_state, enc_outputs)
                target_words = batch_targets[:, t]
                loss += self._loss_fn(target_words, predict_words)
                dec_inputs = tf.expand_dims(target_words, 1)
                
        batch_loss = loss / batch_size
        variables = self.encoder.trainable_variables + self.decoder.trainable_variables
        gradients = tape.gradient(loss, variables)
        self.optimizer.apply_gradients(zip(gradients, variables))
        return batch_loss


    def validate_batch(self, batch_inputs, batch_targets):
        """ Validation during the training cycle. Loss is not backproped.
        batch_inp and batch_targ should be zero-padded.
        """
        assert len(batch_inputs) == len(batch_targets), 'len(batch_inp) does not equal len(batch_targ)'
        batch_size = batch_inputs.shape[0]
        loss = 0
        
        


    def predict(self, inputs, max_output_len):
        pass


    def save(self):
        self.checkpoint.save(self.filename)


    def load(self):
        self.filename
        pass


    def _loss_fn(self, targets, predictions):
        loss = self.loss_obj(targets, predictions)
        mask = tf.math.logical_not(tf.math.equal(targets, 0))
        mask = tf.cast(mask, dtype=loss.dtype)
        loss *= mask
        return tf.math.reduce_mean(loss)


class Encoder(tf.keras.Model):

    def __init__(self, vocab_size, embedding_dim, units, num_layers, dropout=0.):
        super(Encoder, self).__init__()
        self.units = units
        self.embedding_dim = embedding_dim
        self.embedding = layers.Embedding(vocab_size, embedding_dim, mask_zero=True)
        gru_cells = [layers.GRUCell(units,
                                    recurrent_initializer='glorot_uniform',
                                    dropout=dropout)
                     for _ in range(num_layers)]
        self.gru = layers.Bidirectional(layers.RNN(gru_cells,
                                                   return_sequences=True,
                                                   return_state=True))


    def call(self, inputs, state):
        # inputs are in mini-batches
        inputs = self.embedding(inputs)
        outputs, state = self.gru(inputs, initial_state=state)
        return outputs, state


class Decoder(tf.keras.Model):
    
    def __init__(self, vocab_size, embedding_dim, units, num_layers, dropout=0.):
        super(Decoder, self).__init__()
        self.units = units
        self.embedding_dim = embedding_dim
        self.embedding = layers.Embedding(vocab_size, embedding_dim)
        self.attention = BahdanauAttention(units)
        gru_cells = [layers.GRUCell(units,
                                    recurrent_initializer='glorot_uniform',
                                    dropout=dropout)
                     for _ in range(num_layers)]
        self.gru = layers.Bidirectional(layers.RNN(gru_cells,
                                                   return_sequences=True,
                                                   return_state=True))
        self.predictor = tf.keras.layers.Dense(vocab_size)


    def call(self, inputs, state, enc_outputs):
        # enc_outputs shape == (batch_size, max_len, state_size)
        context_vec, _ = self.attention(state, enc_outputs)
        inputs = self.embedding(inputs)
        inputs = tf.concat([tf.expand_dims(context_vec, 1), inputs], axis=-1)
        # x.shape == (batch_size, 1, embedding_dim + state_size)

        outputs, state = self.gru(inputs)
        outputs = tf.reshape(outputs, (-1, outputs.shape[2]))
        predictions = self.predictor(outputs)
        # predictions.shape == (batch_size, vocab_size)
        
        return predictions, state


class BahdanauAttention(layers.Layer):

    def __init__(self, units):
        super(BahdanauAttention, self).__init__()
        self.hidden = layers.Dense(units)
        self.context = layers.Dense(units)
        self.score = tf.keras.layers.Dense(1)


    def call(self, hidden, enc_outputs):
        expanded_hidden = tf.expand_dims(hidden, 1)
        # expanded_hidden.shape == (batch_size, 1, hidden_size)
        # enc_outputs.shape == (batch_size, max_len, hidden_size)

        score = self.score(tf.nn.tanh(self.hidden(expanded_hidden) + self.context(enc_outputs)))
        # score.shape == (batch_size, max_len, 1)

        attn_weights = tf.nn.softmax(score, axis=1)
        # attn_weights shape == (batch_size, max_len, 1)

        context_vec = attn_weights * enc_outputs
        context_vec = tf.reduce_sum(context_vec, axis=1)
        # context_vec.shape == (batch_size, hidden_size)

        return context_vec, attn_weights
